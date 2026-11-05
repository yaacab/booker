export type SceneReturnMode = 'ready' | 'reg';
export interface SceneRecoveryTarget extends EventTarget {
  readonly sessionStorage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
}
const RETURN_KEY = 'booker.scene01.returnToRoles';

/** A BFCache restore preserves the role-departure animation and React selection.
 * Remount that scene on pageshow; remember the role screen for a full reload too.
 * Safari/private browsing may deny storage, so BFCache also has an in-memory flag.
 */
export function installSceneRecovery(target: SceneRecoveryTarget, recover: (mode: SceneReturnMode) => void) {
  const readReturn = () => {
    try { return target.sessionStorage.getItem(RETURN_KEY) === '1'; }
    catch { return false; }
  };
  let returningToRoles = readReturn();
  const onShow: EventListener = event => {
    const remembered = returningToRoles || readReturn();
    if ((event as Event & { persisted?: boolean }).persisted || remembered) {
      recover(remembered ? 'reg' : 'ready');
    }
  };
  target.addEventListener('pageshow', onShow);
  if (returningToRoles) recover('reg');
  return {
    markRoleNavigation() {
      returningToRoles = true;
      try { target.sessionStorage.setItem(RETURN_KEY, '1'); } catch { /* in-memory fallback */ }
    },
    clearReturn() {
      returningToRoles = false;
      try { target.sessionStorage.removeItem(RETURN_KEY); } catch { /* storage may be denied */ }
    },
    dispose() { target.removeEventListener('pageshow', onShow); },
  };
}
