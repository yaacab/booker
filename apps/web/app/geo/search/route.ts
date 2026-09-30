import { NextRequest, NextResponse } from "next/server";
const cache = new Map<string, unknown>();
let lastRequest = 0;
export async function GET(request: NextRequest) {
 const query = (request.nextUrl.searchParams.get("q") || "").trim();
 if (!query || query.length > 220) return NextResponse.json({error:"Укажите район или адрес Москвы"},{status:400});
 if(cache.has(query)) return NextResponse.json(cache.get(query));
 if(Date.now()-lastRequest<1200) return NextResponse.json({error:"Подождите секунду и повторите выбор"},{status:429});
 lastRequest=Date.now();
 try {
 const params=new URLSearchParams({q:`Москва, ${query}`,format:"jsonv2",limit:"1",countrycodes:"ru",viewbox:"36.7,56.2,38.3,55.1",bounded:"1"});
 const response=await fetch(`https://nominatim.openstreetmap.org/search?${params}`,{headers:{"User-Agent":"BukerGo/1.0 (https://bukergo.ru; hello@bukergo.ru)","Accept-Language":"ru"},signal:AbortSignal.timeout(8000),cache:"no-store"});
 if(!response.ok) throw new Error();
 const items=await response.json();const p=items[0];
 const result=p?{lat:Number(p.lat),lon:Number(p.lon),label:p.display_name}:null;
 if(cache.size>=200) cache.delete(cache.keys().next().value as string);
 cache.set(query,result);return NextResponse.json(result);
 } catch {return NextResponse.json({error:"Поиск адреса временно недоступен. Список площадок продолжает работать."},{status:503})}
}
