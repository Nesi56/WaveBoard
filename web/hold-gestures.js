// Holds use fresh landmark observations, never extrapolated finger poses.
export const HOME_HOLD_MS = 3000;
export const EDGE_HOLD_MS = 650;
export const EDGE_REPEAT_MS = 900;
const OBSERVATION_GAP_MS = 450;

export class HoldGestures {
  constructor() { this.reset(); }
  reset() { this.hold = null; }

  update(pointer, position, context, now) {
    if (!pointer.visible || pointer.cancelled || pointer.down || !position || context.hidden) {
      this.reset();
      return null;
    }
    if (this.hold && (this.hold.hand !== pointer.hand || now - this.hold.observedAt > OBSERVATION_GAP_MS)) this.reset();
    // Flow can keep a cursor moving between model frames. It cannot confirm a
    // pose, advance a timer action, or silently change the held direction.
    if (pointer.observed === false || pointer.predicted) return null;
    const observation = Number.isFinite(pointer.observation_timestamp) ? pointer.observation_timestamp : now;
    if (pointer.tracking_age_ms > OBSERVATION_GAP_MS) { this.reset(); return null; }
    if (this.evidenceHand === pointer.hand && this.evidenceAt !== undefined) {
      if (observation <= this.evidenceAt) return null;
      if (observation - this.evidenceAt > OBSERVATION_GAP_MS) this.reset();
    }
    this.evidenceAt = observation;
    this.evidenceHand = pointer.hand;
    let kind = null, direction = 0;
    if (pointer.pose === 'peace') kind = 'home';
    else if (pointer.pose === 'point' && !context.blocked && ['home', 'slides'].includes(context.page)) {
      const x = position[0];
      const previous = this.hold?.kind === 'edge' ? this.hold.direction : 0;
      direction = x <= (previous === -1 ? 0.20 : 0.16) ? -1 :
        x >= (previous === 1 ? 0.80 : 0.84) ? 1 : 0;
      if (direction) kind = 'edge';
    }
    if (!kind) { this.reset(); return null; }
    const key = `${kind}:${direction}:${kind === 'edge' ? context.page : ''}`;
    if (!this.hold || this.hold.key !== key) {
      this.hold = { key, kind, direction, hand: pointer.hand, started: now, startedObservation: observation, observedAt: now,
        fired: kind === 'home' && context.page === 'home', nextAt: now + EDGE_HOLD_MS };
    }
    const hold = this.hold;
    hold.observedAt = now;
    hold.observationElapsed = observation - hold.startedObservation;
    if (kind === 'home' && !hold.fired && Math.min(now - hold.started, hold.observationElapsed) >= HOME_HOLD_MS) {
      hold.fired = true;
      return { home: true };
    }
    if (kind === 'edge' && now >= hold.nextAt && hold.observationElapsed >= (hold.repeating ? EDGE_REPEAT_MS : EDGE_HOLD_MS)) {
      // At most one move per observation, even after a delayed frame.
      hold.started = now;
      hold.startedObservation = observation;
      hold.observationElapsed = 0;
      hold.nextAt = now + EDGE_REPEAT_MS;
      hold.repeating = true;
      return { direction };
    }
    return null;
  }

  progress(now) {
    const hold = this.hold;
    if (!hold || now - hold.observedAt > OBSERVATION_GAP_MS || hold.fired) return null;
    const duration = hold.kind === 'home' ? HOME_HOLD_MS : hold.repeating ? EDGE_REPEAT_MS : EDGE_HOLD_MS;
    return { kind: hold.kind, direction: hold.direction,
      value: Math.max(0, Math.min(1, Math.min(now - hold.started, hold.observationElapsed + now - hold.observedAt) / duration)) };
  }
}
