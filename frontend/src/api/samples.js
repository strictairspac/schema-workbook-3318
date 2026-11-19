import {api} from './client.js';
export const samplesApi={list:()=>api('/samples'),create:data=>api('/samples','POST',data),correct:(id,data)=>api('/samples/'+id,'PUT',data),revisions:id=>api('/samples/'+id+'/revisions'),history:id=>api('/samples/'+id+'/history')};
