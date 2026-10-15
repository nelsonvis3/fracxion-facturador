import { apiRequest } from "./api";
import type { Page } from "./business-api";
export type AccountSession={id:string;device:string;ip_address:string|null;first_seen:string;last_seen:string;expires_at:string;current:boolean};
export const accountSecurityApi={
  emailStatus:()=>apiRequest<{email:string;verified:boolean;verified_at:string|null}>("/api/auth/email-verification/"),
  requestEmailVerification:()=>apiRequest<{detail:string}>("/api/auth/email-verification/request/",{method:"POST",body:"{}"}),
  verifyEmail:(token:string)=>apiRequest<{detail:string}>("/api/auth/email-verification/confirm/",{method:"POST",body:JSON.stringify({token})}),
  sessions:(page=1)=>apiRequest<Page<AccountSession>>(`/api/auth/sessions/?page=${page}`),
  revoke:(id:string)=>apiRequest<{detail:string;current:boolean}>(`/api/auth/sessions/${encodeURIComponent(id)}/revoke/`,{method:"POST",body:"{}"}),
  revokeOthers:(current_password:string)=>apiRequest<{detail:string}>("/api/auth/sessions/revoke-others/",{method:"POST",body:JSON.stringify({current_password})}),
  changePassword:(data:{current_password:string;password:string;password_confirm:string})=>apiRequest<{detail:string}>("/api/auth/password/change/",{method:"POST",body:JSON.stringify(data)}),
};
