import fs from "node:fs/promises";
import path from "node:path";

export type DiscoveryVenue = {id:string;name:string;address:string;metro:string;description:string;capacity:number;price:number;source:string;photos:string[];sound:boolean;light:boolean;districtId:string|null;district:string|null};
async function readData(name:string){
  for(const base of [path.resolve(process.cwd(),"../../data"),path.resolve(process.cwd(),"data")]){
    try{return JSON.parse(await fs.readFile(path.join(base,name),"utf8"))}catch{/* Try the repository root for development entry points. */}
  }
  throw new Error(`Research data unavailable: ${name}`);
}
export async function loadDiscoveryVenues():Promise<DiscoveryVenue[]>{
  const [research,geo]=await Promise.all([readData("moscow_performance_venues_research.json"),readData("moscow_venue_districts.json")]);
  const districts=new Map<string,{district_id?:string;district?:string}>(geo.items.map((r:{id:string;district_id?:string;district?:string})=>[r.id,r]));
  return research.venues.map((r:{source_id:string;name:string;address:string;metro:string;description:string;capacity:number;tariff_from_rub:number;source_url:string;photos:{photo_url:string}[];has_sound:boolean;has_light:boolean})=>({id:r.source_id,name:r.name,address:r.address,metro:r.metro,description:r.description,capacity:r.capacity,price:r.tariff_from_rub,source:r.source_url,photos:r.photos.map(p=>p.photo_url),sound:r.has_sound,light:r.has_light,districtId:districts.get(r.source_id)?.district_id||null,district:districts.get(r.source_id)?.district||null}));
}
