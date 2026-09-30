"use client";
import {useState} from "react";
import {useRouter} from "next/navigation";
import {loadStoredDraft,saveStoredDraft} from "./event-studio/adapter";
import {EMPTY_DRAFT} from "./event-studio/types";
export function AddToAssembly({id,kind}:{id:string;kind:"artist"|"venue"}){const router=useRouter();const [error,setError]=useState("");return <><button className="btn secondary" onClick={()=>{try{const old=loadStoredDraft()?.draft||EMPTY_DRAFT;saveStoredDraft({...old,...(kind==="artist"?{talentIds:Array.from(new Set([...old.talentIds,id]))}:{venueId:id}),version:old.version+1});router.push("/assemble")}catch{setError("Не удалось сохранить выбор на устройстве")}}}>Добавить в сборку события +</button>{error&&<p role="alert">{error}</p>}</>}
