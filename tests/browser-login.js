async (page) => {
  // Local development only: the mail is captured by Mailpit, never delivered externally.
  await page.goto('http://localhost:5173');
  await page.getByRole('textbox', { name: '電子信箱', exact: true }).fill('friend@example.com');
  await page.getByRole('button', { name: '取得驗證碼' }).click();
  await page.getByRole('heading', { name: '輸入驗證碼' }).waitFor();
  const messages = await (await page.request.get('http://127.0.0.1:8025/api/v1/messages')).json();
  const latest = messages.messages.find(m => m.To.some(t => t.Address === 'friend@example.com'));
  if (!latest) throw new Error('No captured login message');
  const message = await (await page.request.get(`http://127.0.0.1:8025/api/v1/message/${latest.ID}`)).json();
  const code = message.Text.match(/\b\d{6}\b/)[0];
  await page.getByRole('textbox', { name: '6 位數驗證碼' }).fill(code);
  await page.getByRole('button', { name: '驗證並進入手記' }).click();
  await page.getByRole('heading', { name: '歡迎回來，旅人' }).waitFor();
  await page.reload();
  await page.getByRole('heading', { name: '歡迎回來，旅人' }).waitFor();
  await page.getByRole('button', { name: /登出/ }).click();
  await page.getByRole('heading', { name: '旅人登入' }).waitFor();
  await page.setViewportSize({width:390,height:844});
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
    throw new Error('Mobile horizontal overflow');
  }
  await page.screenshot({path:'.playwright-cli/login-mobile.png',fullPage:true});
  await page.setViewportSize({width:1280,height:800});
  await page.screenshot({path:'.playwright-cli/login-desktop.png',fullPage:true});
  console.log('PASS: real SMTP/Neo4j login, page reload session, logout, mobile overflow');
}
