import DevelopmentCabinets from "@/components/DevelopmentCabinets";
export const dynamic="force-dynamic";
export default function Page(){return <DevelopmentCabinets enabled={process.env.BOOKER_DEMO_GATEWAY === "1"}/>;}
