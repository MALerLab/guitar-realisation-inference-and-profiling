// Turn one optimiser run file (JSON from `run_optimiser.py --save`) into alphaTex text for alphaTab.
// One track per realisation, cheapest first. The text only lives in memory; nothing is written.
//
// Shown per note: string + fret, pick stroke (sd / su), fretting finger (lf), hammer-on / pull-off
// and slide arcs, left-hand tap; the hand position as text whenever it changes.
// Bar lines go before notes the source marks as a bar start. The passage keeps no bar start
// times, so a rest that crosses a bar line is drawn before the line: bars can look uneven,
// but playback timing is exact (every note and rest keeps its length).

const TICKS_PER_WHOLE = 3840;  // 960 ticks per quarter note, as in the passage
const NOTE_NAMES = ['c', 'c#', 'd', 'd#', 'e', 'f', 'f#', 'g', 'g#', 'a', 'a#', 'b'];
const STROKE_PROPERTY = { D: 'sd', U: 'su' };
const ORIGIN_PROPERTY = { h: 'h', p: 'h', s: 'sl' };  // marked on the note the arc starts from

// Every note value alphaTex can write as one beat: plain, dotted, triplet; longest first
const NOTE_VALUES = [1, 2, 4, 8, 16, 32, 64]
  .flatMap((value) => [
    { value, dotted: true, triplet: false, ticks: (TICKS_PER_WHOLE / value) * 1.5 },
    { value, dotted: false, triplet: false, ticks: TICKS_PER_WHOLE / value },
    { value, dotted: false, triplet: true, ticks: (TICKS_PER_WHOLE / value) * (2 / 3) },
  ])
  .sort((a, b) => b.ticks - a.ticks);

/** MIDI pitch → alphaTex note name, e.g. 64 → "e4". */
function pitchName(pitch) {
  return `${NOTE_NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

/** Split a length in ticks into note values that tie together (longest first; leftovers < 1/96 note dropped). */
function splitTicks(ticks) {
  const pieces = [];
  let remaining = ticks;
  while (remaining >= NOTE_VALUES[NOTE_VALUES.length - 1].ticks - 1e-6) {
    const piece = NOTE_VALUES.find((candidate) => candidate.ticks <= remaining + 1e-6);
    pieces.push(piece);
    remaining -= piece.ticks;
  }
  return pieces;
}

/** Duration suffix + beat properties for one piece, e.g. ".8" and ["d"]. */
function pieceDuration(piece) {
  const properties = [];
  if (piece.dotted) properties.push('d');
  if (piece.triplet) properties.push('tu 3');
  return { suffix: `.${piece.value}`, properties };
}

/** alphaTex for one beat: content, duration, beat properties. */
function beatText(content, piece, extraProperties = []) {
  const { suffix, properties } = pieceDuration(piece);
  const all = [...extraProperties, ...properties];
  return `${content}${suffix}` + (all.length ? ` {${all.join(' ')}}` : '');
}

/** Quote text for alphaTex. */
function quoted(text) {
  return `"${String(text).replaceAll('"', "'")}"`;
}

/** Rest beats covering `ticks`, the first one carrying `label` as text. */
function restBeats(ticks, label = null) {
  return splitTicks(ticks).map((piece, index) =>
    beatText('r', piece, index === 0 && label ? [`txt ${quoted(label)}`] : []));
}

/**
 * The beats of one realisation, in time order.
 *
 * @param run The run file contents.
 * @param realisation One entry of run.realisations.
 */
function realisationBeats(run, realisation) {
  const notes = run.passage.notes;
  const choices = realisation.choices;
  const beats = [];
  let lastHand = null;
  notes.forEach((note, index) => {
    const choice = choices[index];
    const next = notes[index + 1];
    // A note sounds until the next onset at most; the rest of the gap becomes a rest
    const gapTicks = next ? next.onset_tick - note.onset_tick : note.duration_tick;
    const soundTicks = Math.min(note.duration_tick, gapTicks);
    if (index > 0 && note.bar_start) beats.push('|');

    if (choice.string === null) {
      beats.push(...restBeats(soundTicks, note.null_reason ?? 'null'));
    } else {
      // Note properties: finger, arc to the next note, left-hand tap
      const noteProperties = [];
      if (choice.finger > 0) noteProperties.push(`lf ${choice.finger + 1}`);  // alphaTex lf 1 = thumb
      const nextLetter = next ? choices[index + 1].stroke_letter : null;
      if (nextLetter in ORIGIN_PROPERTY) noteProperties.push(ORIGIN_PROPERTY[nextLetter]);
      if (choice.stroke_letter === 't') noteProperties.push('lht');
      // Beat properties: pick stroke, hand position when it moves, marks with no symbol here
      const beatProperties = [];
      if (choice.stroke_letter in STROKE_PROPERTY) beatProperties.push(STROKE_PROPERTY[choice.stroke_letter]);
      const labels = [];
      if (choice.hand !== lastHand) labels.push(`hand ${choice.hand}`);
      if (choice.stroke_letter === 'H') labels.push('H (hammer-on from nowhere)');
      if (note.articulations.includes('bend')) labels.push('bend');
      if (labels.length) beatProperties.push(`txt ${quoted(labels.join(' · '))}`);
      lastHand = choice.hand;

      const position = `${choice.fret}.${choice.string}`;
      splitTicks(soundTicks).forEach((piece, pieceIndex) => {
        const first = pieceIndex === 0;
        const properties = first ? noteProperties : ['t'];
        const content = position + (properties.length ? `{${properties.join(' ')}}` : '');
        beats.push(beatText(content, piece, first ? beatProperties : []));
      });
    }
    if (gapTicks > soundTicks) beats.push(...restBeats(gapTicks - soundTicks));
  });
  return beats;
}

/**
 * alphaTex for a whole run: one track per realisation.
 *
 * @param run The run file contents (format grip_optimiser_run).
 * @param title Title shown above the score.
 */
export function runToTex(run, title) {
  const tuning = run.passage.guitar.tuning.map(pitchName).join(' ');
  const lines = [`\\title (${quoted(title)})`, `\\tempo (${Math.round(run.passage.tempo_bpm)})`];
  for (const realisation of run.realisations) {
    lines.push(
      `\\track (${quoted(`#${realisation.rank} · cost ${realisation.total_cost.toFixed(2)}`)})`,
      '\\staff {tabs}',
      `\\tuning (${tuning})`,
      realisationBeats(run, realisation).join(' '),
    );
  }
  return lines.join('\n');
}
