import { test, expect } from '@playwright/test';

test('путь артиста: преимущества → короткая регистрация → кабинет', async ({page,request}) => {
  await page.goto('/');
  await page.locator('.hero-path-artist').click();
  await expect(page).toHaveURL(/\/for-artists$/);
  await expect(page.getByRole('heading',{name:'Ты создаёшь атмосферу. Мы помогаем встретиться.'})).toBeVisible();
  await expect(page.locator('input[name=kind]')).toHaveValue('artist');
  await expect(page.locator('.role-picker')).toHaveCount(0);
  await page.getByLabel('Имя',{exact:true}).fill('Артист проверки нового входа');
  await page.getByLabel('Email',{exact:true}).fill(`artist-welcome-${Date.now()}@booker.test`);
  await page.getByLabel('Пароль',{exact:true}).fill('Artist-welcome-2026');
  await page.locator('#accept_offer').check();
  await page.locator('#accept_privacy').check();
  await page.getByRole('button',{name:'Создать кабинет артиста →',exact:true}).click();
  await expect(page).toHaveURL(/\/cabinet\/performer/, {timeout:30000});
  const token=await page.evaluate(()=>localStorage.getItem('booker.token'));
  const res=await request.get('http://127.0.0.1:8035/me',{headers:{Authorization:`Bearer ${token}`}});
  expect(res.ok()).toBeTruthy();
  expect((await res.json()).organizations.some((o:{kind:string})=>o.kind==='artist')).toBeTruthy();
});

test('обе темы и мобильный экран; пазлы реагируют и поддерживают reduced motion',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  for(const width of [1440,768,390])for(const edition of ['light','black']){
    await page.setViewportSize({width,height:1000});await page.goto('/for-artists');
    await page.evaluate(value=>{localStorage.setItem('booker.edition',value);document.documentElement.dataset.edition=value},edition);
    await expect(page.locator('input[name=full_name]')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath(`artist-${width}-${edition}.png`),fullPage:true});
    await page.goto('/');
    await page.getByRole('button',{name:/Событие Ваша идея/}).click();
    await expect(page.locator('#artist-first-detail')).toContainText('Выберите артиста');
    await page.getByRole('button',{name:'↻ Собрать ещё раз'}).click();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  await expect(page.locator('.artist-first-puzzles')).toHaveCSS('animation-name','none');
  await expect(page.locator('.artist-first-piece').first()).toHaveCSS('transition-duration','0s');
  expect(errors).toEqual([]);
});
