/**
 * Campaign OS Drive bridge (Google Apps Script web app).
 *
 * Lets Campaign OS do three small things in Drive that it cannot do on its own (it only reads
 * public folders): move a file to another folder, change the text of a .txt caption, and create a
 * new .txt caption. Nothing else: no delete, no sharing changes, nothing outside the brand folders.
 *
 * It runs as the person who deploys it, so it can touch only what that person can.
 * Every request must carry the secret token saved in Script properties (BRIDGE_TOKEN).
 * Setup: docs/drive-bridge/SETUP.md
 */

// The brand folders it may touch (the same roots the app's Drive pull uses). A file or folder
// outside the named brand's root is refused.
var ROOTS = {
  'stick': '1k5icaxY3AKBD9z2-oIO6i42PUnq1gYUG',
  'swing-shack': '1n9pHD6hwr7oEfRBAGBriRrsqv_I-qGge'
};

var MAX_TEXT = 5000;

function doPost(e) {
  try {
    var body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    var token = PropertiesService.getScriptProperties().getProperty('BRIDGE_TOKEN');
    if (!token || body.token !== token) return reply_({ ok: false, error: 'forbidden' });
    var rootId = ROOTS[body.brand];
    if (!rootId) return reply_({ ok: false, error: 'unknown brand' });
    if (body.action === 'move') return reply_(move_(rootId, body));
    if (body.action === 'set_text') return reply_(setText_(rootId, body));
    if (body.action === 'create_text') return reply_(createText_(rootId, body));
    if (body.action === 'ping') return reply_({ ok: true, brand: body.brand });
    return reply_({ ok: false, error: 'unknown action' });
  } catch (err) {
    return reply_({ ok: false, error: String(err) });
  }
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// True when `file` (or folder) sits somewhere under the folder with id `rootId`.
function isUnder_(item, rootId) {
  var parents = item.getParents();
  while (parents.hasNext()) {
    var p = parents.next();
    if (p.getId() === rootId || isUnder_(p, rootId)) return true;
  }
  return false;
}

// "Video/3-published" -> the folder, walking down from the root. It must already exist.
function folderAt_(rootId, path) {
  var folder = DriveApp.getFolderById(rootId);
  var parts = String(path || '').split('/').filter(function (s) { return s; });
  if (!parts.length) throw new Error('no destination folder');
  for (var i = 0; i < parts.length; i++) {
    if (parts[i] === '..') throw new Error('bad folder path');
    var it = folder.getFoldersByName(parts[i]);
    if (!it.hasNext()) throw new Error('folder not found: ' + path);
    folder = it.next();
  }
  return folder;
}

function move_(rootId, body) {
  var file = DriveApp.getFileById(body.file_id);
  if (!isUnder_(file, rootId)) return { ok: false, error: 'that file is not in this brand folder' };
  var dest = folderAt_(rootId, body.dest_path);
  file.moveTo(dest);
  return { ok: true, id: file.getId(), name: file.getName(), moved_to: body.dest_path };
}

function setText_(rootId, body) {
  var file = DriveApp.getFileById(body.file_id);
  if (!isUnder_(file, rootId)) return { ok: false, error: 'that file is not in this brand folder' };
  if (file.getMimeType() !== 'text/plain') return { ok: false, error: 'only .txt caption files can be changed' };
  var text = String(body.text || '');
  if (!text.trim()) return { ok: false, error: 'the caption is empty' };
  if (text.length > MAX_TEXT) return { ok: false, error: 'the caption is too long' };
  file.setContent(text);
  return { ok: true, id: file.getId(), name: file.getName() };
}

function createText_(rootId, body) {
  var name = String(body.name || '');
  if (!/^[A-Za-z0-9._-]+\.txt$/.test(name)) return { ok: false, error: 'the file name must end in .txt and use plain characters' };
  var text = String(body.text || '');
  if (!text.trim()) return { ok: false, error: 'the caption is empty' };
  if (text.length > MAX_TEXT) return { ok: false, error: 'the caption is too long' };
  var folder = folderAt_(rootId, body.folder_path);
  var existing = folder.getFilesByName(name);
  if (existing.hasNext()) return { ok: false, error: 'a file with that name is already there' };
  var file = folder.createFile(name, text, 'text/plain');
  return { ok: true, id: file.getId(), name: file.getName() };
}
