// GRIP GP viewer, guitar neck: the tuning label and the fretboard drawing.
// Knows nothing about the rest of the page: callers pass in a tuning and a fret count, and later
// features add their own inputs (e.g. notes to mark) to drawFretboard's options.
// A tuning is open-string MIDI pitches, string 1 (highest) first, as alphaTab, run files and manifests store it.
// Colours and line widths live in viewer.css (the fretboard-* classes).

const NOTE_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
// Frets with one inlay dot, and with two
const SINGLE_DOT_FRETS = [3, 5, 7, 9, 15, 17, 19, 21];
const DOUBLE_DOT_FRETS = [12, 24];
// Drawing units (the SVG scales to the panel's width): space for the string names, one fret, between strings
const LABEL_WIDTH = 30;
const FRET_WIDTH = 40;
const STRING_GAP = 18;
const TOP_MARGIN = 10;
const BOTTOM_MARGIN = 20;
const RIGHT_MARGIN = 10;
const SVG_NAMESPACE = 'http://www.w3.org/2000/svg';

/** A pitch's note name without octave, flats for the black keys (e.g. 63 → "Eb"). */
export function noteName(pitch) {
  return NOTE_NAMES[((pitch % 12) + 12) % 12];
}

/** A tuning as note names, lowest string first (e.g. "D A D G B E"). */
export function tuningText(tuning) {
  return [...tuning].reverse().map(noteName).join(' ');
}

/** One SVG element with its attributes (and text, if given). */
function svgElement(tag, attributes, text = null) {
  const node = document.createElementNS(SVG_NAMESPACE, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== null) node.textContent = text;
  return node;
}

/**
 * Draw an empty fretboard into `container`, replacing what is there: string 1 on top as in tab,
 * each string named by its open note at the nut, frets 1 to `highestFret` evenly spaced, inlay dots.
 *
 * Args:
 *   container: The element to draw into.
 *   options.tuning: Open-string MIDI pitches, string 1 first; one line is drawn per string.
 *   options.highestFret: How many frets the neck has.
 */
export function drawFretboard(container, { tuning, highestFret }) {
  const stringCount = tuning.length;
  const nutX = LABEL_WIDTH;
  const endX = nutX + highestFret * FRET_WIDTH;
  const topY = TOP_MARGIN;
  const bottomY = topY + (stringCount - 1) * STRING_GAP;
  const fretCentreX = (fret) => nutX + (fret - 0.5) * FRET_WIDTH;
  const svg = svgElement('svg', {
    class: 'fretboard', viewBox: `0 0 ${endX + RIGHT_MARGIN} ${bottomY + BOTTOM_MARGIN}`,
    role: 'img', 'aria-label': `Fretboard: ${tuningText(tuning)}, ${highestFret} frets`,
  });

  // Wood, then the inlay dots on it
  svg.append(svgElement('rect', { class: 'fretboard-wood', x: nutX, y: topY, width: endX - nutX, height: bottomY - topY }));
  const middleY = (topY + bottomY) / 2;
  for (const fret of SINGLE_DOT_FRETS.filter((fret) => fret <= highestFret)) {
    svg.append(svgElement('circle', { class: 'fretboard-dot', cx: fretCentreX(fret), cy: middleY, r: 4 }));
  }
  for (const fret of DOUBLE_DOT_FRETS.filter((fret) => fret <= highestFret)) {
    for (const y of [topY + (bottomY - topY) / 4, topY + (3 * (bottomY - topY)) / 4]) {
      svg.append(svgElement('circle', { class: 'fretboard-dot', cx: fretCentreX(fret), cy: y, r: 4 }));
    }
  }

  // Nut and frets, with the dotted frets numbered underneath
  svg.append(svgElement('line', { class: 'fretboard-nut', x1: nutX, y1: topY, x2: nutX, y2: bottomY }));
  for (let fret = 1; fret <= highestFret; fret += 1) {
    const x = nutX + fret * FRET_WIDTH;
    svg.append(svgElement('line', { class: 'fretboard-fret', x1: x, y1: topY, x2: x, y2: bottomY }));
    if (SINGLE_DOT_FRETS.includes(fret) || DOUBLE_DOT_FRETS.includes(fret)) {
      svg.append(svgElement('text', { class: 'fretboard-fret-number', x: fretCentreX(fret), y: bottomY + 15 }, fret));
    }
  }

  // Strings, thicker towards the low ones, each named by its open note
  tuning.forEach((pitch, index) => {
    const y = topY + index * STRING_GAP;
    const width = 1 + (1.5 * index) / Math.max(stringCount - 1, 1);
    svg.append(svgElement('line', { class: 'fretboard-string', x1: nutX, y1: y, x2: endX, y2: y, 'stroke-width': width }));
    svg.append(svgElement('text', { class: 'fretboard-string-name', x: nutX - 8, y: y + 4 }, noteName(pitch)));
  });
  container.replaceChildren(svg);
}
