import argparse
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from kdh.app import create_app
from kdh.core import TYPES, now, pack, uid


def main():
    parser = argparse.ArgumentParser(description='KDH Report Admin')
    parser.add_argument('command', choices=['serve', 'create-admin', 'reset-password', 'seed-demo'], nargs='?', default='serve')
    parser.add_argument('--email')
    args = parser.parse_args()
    app = create_app()
    store = app.extensions['store']
    if args.command == 'seed-demo':
        from kdh.demo import seed_demo
        actor = store.one("SELECT id FROM users WHERE role='admin' AND active=1 ORDER BY created_at LIMIT 1")
        if not actor:
            sys.exit('Tạo tài khoản admin trước khi thêm dữ liệu demo.')
        print(pack(seed_demo(store, actor['id'])))
        return
    if args.command != 'serve':
        email = (args.email or input('Email: ')).strip().lower()
        password = getpass.getpass('Mật khẩu mới (ít nhất 12 ký tự): ')
        if len(password) < 12 or password != getpass.getpass('Nhập lại mật khẩu: '):
            sys.exit('Mật khẩu không hợp lệ hoặc không khớp.')
        if args.command == 'create-admin':
            store.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)',
                          (uid(), email, 'Quản trị viên', generate_password_hash(password), 'admin', pack(list(TYPES)), 1, now()))
        else:
            with store.connect(immediate=True) as db:
                result = db.execute('UPDATE users SET password=? WHERE email=?', (generate_password_hash(password), email))
                if not result.rowcount:
                    sys.exit('Không tìm thấy tài khoản.')
                db.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)', (email,))
        print('Đã cập nhật tài khoản.')
        return
    # The durable worker is single-process. Enforce a process lock, released by the OS on exit.
    lockfile = (store.folder / 'server.lock').open('a+b')
    lockfile.write(b'0'); lockfile.flush(); lockfile.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit('KDH Report Admin đã chạy với cơ sở dữ liệu này.')
    app.extensions['worker'].start()
    from waitress import serve
    host, port = os.getenv('HOST', '127.0.0.1'), int(os.getenv('PORT', '8090'))
    print(f'KDH Report Admin: http://{host}:{port}', flush=True)
    serve(app, host=host, port=port, threads=8, max_request_body_size=5*1024*1024)


if __name__ == '__main__':
    main()
