import DevelopmentCabinets from "@/components/DevelopmentCabinets";
export const dynamic="force-dynamic";
export default function Page(){
 const enabled=process.env.BOOKER_DEMO_GATEWAY === "1";
 const credentials=enabled?Object.fromEntries(Object.entries({customer:"customer@booker.test",performer:"artist@booker.test",venue:"venue@booker.test",admin:"admin@booker.test"}).map(([role,email])=>[role,{email,password:"password1"}])):{};
 return <DevelopmentCabinets enabled={enabled} credentials={credentials}/>;
}
