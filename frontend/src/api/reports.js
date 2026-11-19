import {api,download} from './client.js';
export const reportsApi={list:()=>api('/reports'),create:data=>api('/reports','POST',data),export:id=>download('reports',id)};
