import {samplesApi} from '../api/samples.js';
export const samplesStore={items:[],async refresh(){this.items=await samplesApi.list();return this.items;}};
