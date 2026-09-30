import {NextRequest,NextResponse} from "next/server";
export const dynamic="force-dynamic";
async function proxy(req:NextRequest,{params}:{params:Promise<{path:string[]}>}){
 if(process.env.BOOKER_DEMO_GATEWAY!=="1")return new NextResponse(null,{status:404});
 const {path}=await params;
 if(path.some(p=>p===".."||p.includes("/")||p.includes("\\")))return new NextResponse(null,{status:400});
 try{const headers=new Headers();for(const name of ["authorization","content-type","x-booker-org"]) {const value=req.headers.get(name);if(value)headers.set(name,value)}
 const body=["GET","HEAD"].includes(req.method)?undefined:await req.arrayBuffer();
 if(body&&body.byteLength>6*1024*1024)return new NextResponse(null,{status:413});
 const result=await fetch(`http://127.0.0.1:8031/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`,{method:req.method,headers,body,cache:"no-store",redirect:"manual",signal:AbortSignal.timeout(15000)});
 const responseHeaders=new Headers({"Cache-Control":"no-store","X-Robots-Tag":"noindex"});const type=result.headers.get("content-type");if(type)responseHeaders.set("Content-Type",type);
 return new NextResponse(result.status===204?null:await result.arrayBuffer(),{status:result.status,headers:responseHeaders});
 }catch{return NextResponse.json({detail:"Демонстрационный контур временно недоступен"},{status:503})}
}
export {proxy as GET,proxy as POST,proxy as PUT,proxy as PATCH,proxy as DELETE};
