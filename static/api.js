let csrf = '';
let sessionVersion = 0;
export function setCsrf(value) { const next=value||''; if(next!==csrf)sessionVersion++; csrf=next; }
export async function api(path, method = 'GET', data) {
  const requestSession = sessionVersion;
  const options = {method, credentials:'same-origin', headers:{'X-KDH-Request':'1','X-CSRF-Token':csrf}};
  if (data instanceof FormData) options.body = data;
  else if (data !== undefined) { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(data); }
  const response = await fetch('/api'+path,options);
  const payload = await response.json().catch(()=>({error:'Máy chủ trả về phản hồi không hợp lệ.'}));
  // Never deliver an old account's response after logout or a new login.
  if (requestSession !== sessionVersion) { const err=new Error('Phiên đăng nhập đã thay đổi.'); err.cancelled=true; throw err; }
  if (!response.ok) { const err = new Error(payload.error || 'Không thể thực hiện yêu cầu.'); err.status=response.status; throw err; }
  return payload;
}
