import {packagesApi} from '../api/packages.js';
export const packagesStore={items:[],async refresh(){this.items=await packagesApi.list();return this.items;}};
