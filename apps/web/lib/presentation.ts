export type TechnicalRequirements = {
  stage_area_m2: number | null; power_kw: number | null; basic_sound: boolean | null;
  microphones: number | null; setup_minutes: number | null; teardown_minutes: number | null;
  required_equipment: string[] | null; supplied_equipment: string[] | null;
};
export type ArtistPresentation = {
  name: string; city: string; category: string; cover_url: string; primary_video_url: string;
  gallery: string[]; links: { url: string; label: string; kind: "video" | "audio" }[];
  format: string; lineup: string; program: string; genres: string[]; duration_minutes: number | null;
  travel_cities: string[]; rider_text: string; technical: TechnicalRequirements;
  layout: "standard" | "gallery_first"; media_rights_confirmed: boolean;
};
export type PresentationEnvelope = { version: number; data: ArtistPresentation; limits: { gallery: number; links: number; travel_cities: number; advanced_layout: boolean } };
