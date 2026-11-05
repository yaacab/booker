import { notFound } from "next/navigation";
import DevelopmentCabinets from "@/components/DevelopmentCabinets";
export const dynamic="force-dynamic";
export const metadata = { robots: { index: false, follow: false } };
// Dev/staging only: production has no BOOKER_DEMO_GATEWAY, so the route is a 404 and no credentials are rendered.
export default function Page(){
 if(process.env.BOOKER_DEMO_GATEWAY !== "1") notFound();
 const password=process.env.BOOKER_DEMO_PASSWORD ?? "";
 const credentials=Object.fromEntries(Object.entries({customer:"customer@booker.test",performer:"artist@booker.test",venue:"venue@booker.test",admin:"admin@booker.test"}).map(([role,email])=>[role,{email,password}]));
 return <DevelopmentCabinets enabled credentials={credentials}/>;
}
