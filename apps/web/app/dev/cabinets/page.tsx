import { notFound } from "next/navigation";
import DevelopmentCabinets from "@/components/DevelopmentCabinets";
export const dynamic="force-dynamic";
export default function Page(){
 if(process.env.BOOKER_DEMO_GATEWAY !== "1")notFound();
 const credentials=Object.fromEntries(Object.entries({customer:"customer@booker.test",performer:"artist@booker.test",venue:"venue@booker.test",admin:"admin@booker.test"}).map(([role,email])=>[role,{email,password:"password1"}]));
 return <DevelopmentCabinets enabled credentials={credentials}/>;
}
