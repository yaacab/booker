"use client";

import { HandoffArrival } from "@/components/scene/HandoffArrival";
import { MOTION } from "@/lib/motion";
import { SCENE_ROLES, type SceneRole } from "@/lib/sceneRoles";

/** Scene 01 role card, continued: the photo the user tapped in the intro stays
 *  the anchor and becomes the header of the registration form. */
export function RoleHandoffCard({ role, onArrive }: { role: SceneRole; onArrive?: (hadHandoff: boolean) => void }) {
  const r = SCENE_ROLES[role];
  return (
    <aside className="bk-role-handoff bk-paper" aria-label="Выбранная роль">
      <HandoffArrival channel="role" id={role} className="bk-role-handoff-photo" duration={MOTION.related} onArrive={onArrive}>
        <img key={r.photo} src={r.photo} alt="" width={760} height={560} decoding="async" />
      </HandoffArrival>
      <div className="bk-role-handoff-body">
        <p className="bk-role-handoff-kicker">{r.kicker}</p>
        <p className="bk-role-handoff-title">{r.title}</p>
        <p className="bk-role-handoff-text">{r.text}</p>
        <a className="bk-role-handoff-back" href="/"><span aria-hidden="true">←</span> К выбору роли</a>
      </div>
    </aside>
  );
}
