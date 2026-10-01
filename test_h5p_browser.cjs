// Optional browser QA using the actual H5P 1.27 core copied into an ignored build folder.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('./build/h5p-qa/node_modules/playwright');
const root = __dirname;
const fixture = `<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/vendor/H5P.Video-1.6/styles/video.css">
<link rel="stylesheet" href="/h5p/H5P.LumTrackedVideo-1.0/tracked-video.css">
<style>body{margin:0;font-family:Arial,sans-serif}main{max-width:1000px;margin:auto}</style>
<script>window.H5P={preventInit:true};window.H5PIntegration={saveFreq:30,isFramed:false,
baseUrl:location.origin,siteUrl:location.origin,postUserStatistics:false,l10n:{H5P:{}},user:{name:'Test',mail:'test@example.invalid'},
contents:{'cid-1':{contentUrl:location.origin+'/content',url:location.href,metadata:{title:'Prova H5P'},contentUserData:{0:{}}}}};</script>
<script src="/core/jquery.js"></script><script src="/core/h5p-event-dispatcher.js"></script>
<script src="/core/h5p-x-api-event.js"></script><script src="/core/h5p-x-api.js"></script>
<script src="/core/h5p.js"></script>
<script src="/vendor/H5P.Video-1.6/scripts/html5.js"></script>
<script src="/vendor/H5P.Video-1.6/scripts/video.js"></script>
<script src="/h5p/H5P.LumTrackedVideo-1.0/tracked-video.js"></script></head><body><main id="lesson"></main>
<script>window.statements=[];window.states=[];
H5P.setUserData=function(id,key,state){window.states.push(JSON.parse(JSON.stringify(state)));};
window.addEventListener('load',function(){window.lesson=new H5P.LumTrackedVideo({
lessonTitle:'Video H5P: lezione di prova con un titolo sufficientemente lungo per verificare la finestra mobile',
video:[{path:'videos/video.mp4',mime:'video/mp4'}],duration:4,checkpointSeconds:'30',resume:true},1);
lesson.on('xAPI',function(event){statements.push(JSON.parse(JSON.stringify(event.data.statement)));});
lesson.attach(H5P.jQuery('#lesson'));});</script></body></html>`;

const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost').pathname;
  if (url === '/') { response.setHeader('content-type', 'text/html'); response.end(fixture); return; }
  let file;
  if (url.startsWith('/core/')) file = path.join(root, 'build/h5p-qa', path.basename(url));
  else if (url === '/content/videos/video.mp4') file = path.join(root, 'build/installer/staging/app/sample.mp4');
  else if (url.startsWith('/vendor/') || url.startsWith('/h5p/')) file = path.resolve(root, '.' + url);
  if (!file || !file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.statusCode = 404; response.end(); return;
  }
  response.setHeader('content-type', file.endsWith('.js') ? 'application/javascript' :
    file.endsWith('.css') ? 'text/css' : file.endsWith('.mp4') ? 'video/mp4' : 'application/octet-stream');
  fs.createReadStream(file).pipe(response);
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    for (const [name, viewport] of [['desktop', {width:1280,height:800}], ['mobile', {width:390,height:844}]]) {
      const page = await browser.newPage({viewport});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto('http://127.0.0.1:' + server.address().port);
      await page.waitForFunction(() => window.lesson && lesson.validVideo);
      const video = page.locator('video');
      assert.ok((await video.boundingBox()).width > 250);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.evaluate(() => document.querySelector('video').play());
      await page.waitForFunction(() => window.statements.length === 1);
      const result = await page.evaluate(() => ({statement: statements[0], state: lesson.getCurrentState(),
        percent: document.querySelector('.lum-video-footer span').textContent,
        time: document.querySelector('video').currentTime}));
      assert.equal(result.percent, '100% visto');
      assert.equal(result.statement.result.completion, true);
      assert.equal(result.statement.result.score, undefined);
      assert.ok(result.time > 3.8);
      assert.deepEqual(errors, []);
      await page.screenshot({path:path.join(root,'build/h5p-qa',name+'.png'),fullPage:true});
      console.log(name + ': real H5P video playback completed without score or horizontal overflow');
      await page.close();
    }
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); server.close(); process.exitCode = 1;});
