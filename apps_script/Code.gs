function onAddToSpace(e) {
  return {
    text: 'Thanks for installing OpenRV Bot. Download the compiled RV from https://drive.google.com/file/d/1SFsldpD9mWzKTm9tEKVhW-HwzB8tmC-8/view?usp=sharing, place it in a folder, and run `rv -network` from the `bin` directory before using this bot.'
  };
}

function onRemoveFromSpace(e) {
  return {text: 'OpenRV Bot removed from this space.'};
}

function onMessage(e) {
  var text = '';
  if (e.message) {
    text = e.message.text || e.message.argumentText || '';
  }
  var match = text.match(/gs:\/\/[\S]+/);
  if (match) {
    return {
      text: 'Received sequence URL: ' + match[0] + '\nDownload it locally and use `rvpush` to open the sequence in your running RV session.'
    };
  }
  return {
    text: 'Mention @OpenRV Bot with a `gs://` URL to view a sequence. Uploading files is not implemented in this Apps Script example.'
  };
}
