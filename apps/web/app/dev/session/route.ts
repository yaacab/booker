import {NextRequest,NextResponse} from "next/server";
export async function POST(req:NextRequest){
 if(process.env.BOOKER_DEMO_GATEWAY!=="1")return new NextResponse(null,{status:404});
 try{const {role}=await req.json();const emails:Record<string,string>={customer:"customer@booker.test",performer:"artist@booker.test",venue:"venue@booker.test",admin:"admin@booker.test"};if(!emails[role])return new NextResponse(null,{status:400});
 const response=await fetch("http://127.0.0.1:8031/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:emails[role],password:"password1"}),cache:"no-store",signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error();
 return NextResponse.json(await response.json(),{headers:{"Cache-Control":"no-store","X-Robots-Tag":"noindex"}});
 }catch{return NextResponse.json({error:"Демо-вход временно недоступен. Попробуйте через минуту."},{status:503})}
}
