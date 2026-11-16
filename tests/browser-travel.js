async (page) => {
  await page.goto('http://localhost:5173');
  const emailInput = page.getByRole('textbox', {name:'電子信箱',exact:true});
  if (await emailInput.isVisible()) {
    await emailInput.fill('friend@example.com');
    await page.getByRole('button',{name:'取得驗證碼',exact:true}).click();
    await page.getByRole('heading',{name:'輸入驗證碼'}).waitFor();
    const inbox=await (await page.request.get('http://127.0.0.1:8025/api/v1/messages')).json();
    const msg=inbox.messages.find(m=>m.To.some(t=>t.Address==='friend@example.com'));
    const content=await (await page.request.get(`http://127.0.0.1:8025/api/v1/message/${msg.ID}`)).json();
    await page.getByRole('textbox',{name:'6 位數驗證碼'}).fill(content.Text.match(/\b\d{6}\b/)[0]);
    await page.getByRole('button',{name:'驗證並進入手記'}).click();
  }
  await page.getByRole('heading',{name:'我的旅行手記'}).waitFor();
  await page.getByRole('button',{name:'新增旅程手記',exact:true}).click();
  const tripName='Browser travel '+Date.now();
  await page.locator('#trip-name-input').fill(tripName);
  await page.locator('#trip-start-date').fill('2026-11-01');
  await page.locator('#trip-end-date').fill('2026-11-03');
  await page.getByRole('button',{name:'建立旅程',exact:true}).click();
  const detail=page.getByRole('region',{name:'旅行手記詳情與時間軸'});
  await detail.waitFor();
  for(const name of ['Station','Coffee']) {
    await page.locator('.detail-nav .btn-primary').click();
    if(await page.getByRole('button',{name:'建立新地點',exact:true}).isVisible()) {
      await page.getByRole('button',{name:'建立新地點',exact:true}).click();
    }
    await page.locator('#event-place-name').fill(name);
    await page.locator('#event-city').fill('Tokyo');
    await page.locator('#event-category').fill('Cafe');
    await page.locator('#event-date').fill('2026-11-01');
    await page.locator('#event-notes').fill('A remembered visit');
    await page.getByRole('dialog').getByRole('button',{name:'記錄足跡',exact:true}).click();
    await page.getByRole('dialog').waitFor({state:'hidden'});
  }
  await page.getByRole('button',{name:'將 Coffee 往上移'}).click();
  await page.getByText('已更新足跡順序。',{exact:true}).waitFor();
  await page.reload();
  await page.getByRole('heading',{name:'我的旅行手記'}).waitFor();
  await page.getByRole('button',{name:`檢視手記：${tripName}`}).click();
  await detail.waitFor();
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('Mobile overflow');
  await page.screenshot({path:'.playwright-cli/travel-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:'.playwright-cli/travel-desktop.png',fullPage:true});
  console.log('PASS trip/event creation, reorder, persisted reload and phone layout');
}
