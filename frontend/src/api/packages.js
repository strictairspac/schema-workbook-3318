import {api,download} from './client.js';
export const packagesApi={list:()=>api('/packages'),create:data=>api('/packages','POST',data),detail:id=>api('/packages/'+id),publish:id=>api('/packages/'+id+'/publish'),export:id=>download('packages',id)};
