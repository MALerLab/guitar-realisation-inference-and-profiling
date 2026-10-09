// GRIP GP viewer, file picker: the path box, one box per dataset, and the searchable track list
// (manifest rows from the server). viewer.mjs calls setupFilePicker once at start.

// What viewer.mjs shares, set once by setupFilePicker
let element, pageConfig, openFile;
// Dataset name → its label, for the track list rows
let datasetLabels;

/** Take what viewer.mjs shares, build the dataset boxes and show the first track list. */
export function setupFilePicker(page) {
  ({ element, pageConfig, openFile } = page);
  datasetLabels = Object.fromEntries(pageConfig.datasets.map(({ name, label }) => [name, label]));

  // A path with a folder opens directly; a bare file name is looked up first (openByFileName)
  element('path-form').onsubmit = (event) => {
    event.preventDefault();
    const path = element('path-input').value.trim();
    if (!path) return;
    if (path.includes('/')) openFile(path, 0, tickedDatasets());
    else openByFileName(path);
  };

  // Re-search shortly after typing stops, and on every toggle
  let searchTimer;
  element('search-input').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(refreshTrackList, 250); };
  element('vocal-only').onchange = refreshTrackList;
  buildDatasetBoxes();
  refreshTrackList();
}

/** Names of the datasets whose boxes are ticked. */
function tickedDatasets() {
  return [...document.querySelectorAll('#dataset-boxes input:checked')].map((box) => box.value);
}

/** One ticked box per dataset in the server config. */
function buildDatasetBoxes() {
  element('dataset-boxes').replaceChildren(...pageConfig.datasets.map(({ name, label }) => {
    const box = Object.assign(document.createElement('input'), { type: 'checkbox', value: name, checked: true });
    box.onchange = refreshTrackList;
    const boxLabel = document.createElement('label');
    boxLabel.append(box, ` ${label}`);
    const row = document.createElement('div');
    row.append(boxLabel);
    return row;
  }));
}

/** One list row: song, track, dataset + path, and a warning if alphaTab is known to refuse the file. */
function buildTrackRow(row) {
  const item = document.createElement('li');
  const lines = [
    ['song', `${row.artist ?? '?'} — ${row.title_display ?? '?'}`],
    ['track', `track ${row.track_index}: ${row.track_name} · ${row.guitar_or_bass}`],
    ['file-path', `${datasetLabels[row.dataset] ?? row.dataset} · ${row.path}`],
  ];
  if (row.parse_error) lines.push(['unreadable', `alphaTab can't read this file: ${row.parse_error}`]);
  for (const [className, text] of lines) {
    const line = document.createElement('div');
    line.className = className;
    line.textContent = text;
    item.append(line);
  }
  item.onclick = async () => {
    if (!(await openFile(row.gp_path, row.track_index))) return;
    document.querySelector('#track-list li.selected')?.classList.remove('selected');
    item.classList.add('selected');
  };
  return item;
}

/** Ask the server for manifest tracks in the ticked datasets matching `filters` (see server.search_tracks). */
async function fetchTracks(filters) {
  const params = new URLSearchParams({ datasets: tickedDatasets().join(','), ...filters });
  return (await fetch(`/api/tracks?${params}`)).json();
}

/** Redraw the track list with a server answer, under a count line. */
function showTrackList(result, countText) {
  element('result-count').textContent = countText;
  element('track-list').replaceChildren(...result.rows.map(buildTrackRow));
}

/** Tracks matching the search box + boxes. */
async function refreshTrackList() {
  const result = await fetchTracks({ query: element('search-input').value, vocal_or_melody_only: element('vocal-only').checked ? '1' : '0' });
  showTrackList(result, `${result.total} tracks` + (result.total > result.rows.length ? ` (showing ${result.rows.length})` : ''));
}

/**
 * The path box holds a bare file name (with or without extension): open the one file in the ticked
 * datasets called that, or list the tracks of several to click. No such file: try it as a path
 * (a file directly in a dataset folder), which reports the server's "no file" message if that fails too.
 */
async function openByFileName(fileName) {
  const result = await fetchTracks({ file_name: fileName });
  if (result.file_count === 1) {
    openFile(result.rows[0].gp_path, 0);
  } else if (result.file_count === 0) {
    openFile(fileName, 0, tickedDatasets());
  } else {
    showTrackList(result, `${result.file_count} files named "${fileName}" (${result.total} tracks): click one`);
  }
}
