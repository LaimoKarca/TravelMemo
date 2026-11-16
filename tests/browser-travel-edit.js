async (page) => {
  await page.goto('http://localhost:5173');
  await page.getByRole('heading',{name:'我的旅行手記'}).waitFor();
  const trips=(await (await page.request.get('http://localhost:5173/api/v1/trips')).json()).items;
  let trip;
  for(const t of trips.filter(t=>t.name.startsWith('Browser travel '))) {
    const detail=await (await page.request.get(`http://localhost:5173/api/v1/trips/${t.id}`)).json();
    if(detail.events.length===2) {trip=t;break;}
  }
  if(!trip) throw Error('Run browser-travel.js first');
  await page.getByRole('button',{name:`檢視手記：${trip.name}`}).click();
  await page.locator('.event-card').first().getByRole('button',{name:'編輯',exact:true}).click();
  await page.locator('#event-notes').fill('Verified edited memory');
  await page.getByRole('dialog').getByRole('button',{name:'儲存修改',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByText('Verified edited memory',{exact:true}).waitFor();
  await page.locator('.event-card').first().getByRole('button',{name:'刪除',exact:true}).click();
  await page.getByRole('dialog').locator('.btn-danger').click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  if(await page.locator('.event-card').count()!==1) throw Error('Event delete failed');
  await page.getByRole('button',{name:'返回手記列表',exact:true}).click();
  await page.getByRole('button',{name:`檢視手記：${trip.name}`}).getByRole('button',{name:'刪除手記',exact:true}).click();
  await page.getByRole('dialog').locator('.btn-danger').click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  // Remove only test-created trips, using their current revisions.
  const csrf=(await (await page.request.get('http://localhost:5173/api/v1/auth/me')).json()).csrf_token;
  const remaining=(await (await page.request.get('http://localhost:5173/api/v1/trips')).json()).items;
  for(const t of remaining.filter(t=>t.name.startsWith('Browser travel '))) {
    const r=await page.request.delete(`http://localhost:5173/api/v1/trips/${t.id}?version=${t.version}`,{headers:{'X-CSRF-Token':csrf}});
    if(r.status()!==204) throw Error('Test trip cleanup failed');
  }
  await page.reload();
  await page.getByRole('heading',{name:'我的旅行手記'}).waitFor();
  console.log('PASS editing notes, event deletion, trip deletion, test trip cleanup');
}
