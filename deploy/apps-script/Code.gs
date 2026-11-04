// Fracxion mail relay: paste into script.google.com while signed in to the sending Gmail.
// Project Settings > Script properties: MAIL_SECRET = same value as APPS_SCRIPT_MAIL_SECRET in Render.
// Deploy > New deployment > Web app, Execute as: Me, Who has access: Anyone.
function doPost(e) {
  const secret = PropertiesService.getScriptProperties().getProperty('MAIL_SECRET');
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (error) {
    return reply(false);
  }
  if (!secret || secret.length < 32 || data.secret !== secret || !data.to || !data.subject) {
    return reply(false);
  }
  const options = { name: data.name || 'Fracxion' };
  ['htmlBody', 'replyTo', 'cc', 'bcc'].forEach(function (key) {
    if (data[key]) options[key] = data[key];
  });
  MailApp.sendEmail(data.to, data.subject, data.body || '', options);
  return reply(true);
}

function reply(ok) {
  return ContentService.createTextOutput(JSON.stringify({ ok: ok }))
    .setMimeType(ContentService.MimeType.JSON);
}
