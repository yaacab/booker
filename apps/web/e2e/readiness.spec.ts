import { test, expect, type Page } from "@playwright/test";

const api=process.env.BOOKER_API_URL||"http://127.0.0.1:8035";
async function noOverflow(page:Page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)}

test("главная: обе темы, пазлы, мобильная вёрстка и reduced motion",async({page},info)=>{
  const errors:string[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  for(const width of [1440,768,390]){
    await page.setViewportSize({width,height:1000});
    await page.goto("/");
    await expect(page.getByRole("heading",{level:1})).toContainText("Работа для артистов");
    await expect(page.getByRole("link",{name:/Мне нужен артист/})).toBeVisible();
    await page.getByRole("button",{name:/Событие Ваша идея/}).click();
    await expect(page.locator("#artist-first-detail")).toContainText("Выберите артиста");
    for(const edition of ["light","black"]){
      if(await page.locator("html").getAttribute("data-edition")!==edition)await page.getByRole("button",{name:"Black Edition",exact:true}).click();
      await expect(page.locator("html")).toHaveAttribute("data-edition",edition);
      await noOverflow(page);
      await page.screenshot({path:info.outputPath(`home-${width}-${edition}.png`),fullPage:true,animations:"disabled"});
    }
  }
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.getByRole("button",{name:/Артист Ваш талант/}).click();
  await expect(page.locator(".artist-first-piece").first()).toHaveCSS("transition-duration","0s");
  expect(errors).toEqual([]);
});

test("заказчик и артист: поиск → заявка → предложение → переписка → удержание",async({browser,request},info)=>{
  async function screens(page:Page,label:string){
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:900});
      for(const edition of ["light","black"]){
        if(await page.locator("html").getAttribute("data-edition")!==edition)await page.getByRole("button",{name:"Black Edition",exact:true}).click();
        await noOverflow(page);
        await page.screenshot({path:info.outputPath(`${label}-${width}-${edition}.png`),fullPage:true,animations:"disabled"});
      }
    }
    await page.setViewportSize({width:1440,height:1000});
  }
  const suffix=Date.now();
  async function post(path:string,data:unknown,token?:string){
    const res=await request.post(api+path,{data,headers:token?{Authorization:`Bearer ${token}`}:{}});
    expect(res.ok(),`${path}: ${await res.text()}`).toBeTruthy();return res.json();
  }
  async function get(path:string,token:string){const res=await request.get(api+path,{headers:{Authorization:`Bearer ${token}`}});expect(res.ok()).toBeTruthy();return res.json()}
  async function party(kind:string){
    const user=await post("/auth/register",{email:`readiness-${kind}-${suffix}@booker.test`,password:"Readiness-test-2026",full_name:kind==="artist"?"Тестовый артист":"Тестовый заказчик",phone:"+79000000000",accept_offer:true,accept_privacy:true});
    const org=await post("/orgs",{name:kind==="artist"?"Артист проверки":"Заказчик проверки",kind},user.token);
    return {...user,org};
  }
  const customer=await party("customer"),artist=await party("artist");
  const profile=await post("/artists",{organization_id:artist.org.id,name:`Артист проверки ${suffix}`,city:"Москва",category:"dj"},artist.token);
  await post(`/artists/${profile.id}/tariffs`,{title:"Выступление",honorarium_rub:80000},artist.token);
  const start=new Date();start.setUTCDate(start.getUTCDate()+7);start.setUTCHours(17,0,0,0);
  const end=new Date(start.getTime()+4*3600000);
  await post("/slots",{resource_type:"artist",resource_id:profile.id,starts_at:start.toISOString(),ends_at:end.toISOString()},artist.token);
  const customerContext=await browser.newContext({viewport:{width:1440,height:1000}}),artistContext=await browser.newContext({viewport:{width:1440,height:1000}});
  for(const [ctx,account] of [[customerContext,customer],[artistContext,artist]] as const){await ctx.addInitScript(({token,org})=>{localStorage.setItem("booker.token",token);localStorage.setItem("booker.org",org);},{token:account.token,org:account.org.id});}
  const customerPage=await customerContext.newPage(),artistPage=await artistContext.newPage();
  const base=process.env.BOOKER_WEB_URL||"http://127.0.0.1:4316";
  await customerPage.goto(base+"/search?kind=artist&category=dj");
  await customerPage.locator('input[type="date"][name="date"]').fill(start.toISOString().slice(0,10));
  await customerPage.locator('input[type="date"][name="date"]').press("Enter");
  await expect(customerPage).toHaveURL(new RegExp(`date=${start.toISOString().slice(0,10)}`));
  await expect(customerPage.locator('input[name="category"][type="radio"][value="dj"]')).toBeChecked();
  await expect(customerPage.getByRole("group",{name:"Район и метро Москвы"})).toHaveCount(0);
  await expect(customerPage.getByRole("link",{name:`Открыть профиль: ${profile.name}`,exact:true})).toBeVisible();
  await screens(customerPage,"search");
  await customerPage.getByRole("link",{name:`Открыть профиль: ${profile.name}`,exact:true}).click();
  await expect(customerPage.getByRole("heading",{level:1})).toContainText(profile.name);
  await expect(customerPage.locator(".profile-booking-date")).toContainText("20:00");
  await noOverflow(customerPage);
  await screens(customerPage,"profile");
  const requested=customerPage.waitForResponse(r=>r.url().endsWith("/quick-request")&&r.request().method()==="POST");
  await customerPage.locator("button.profile-primary-action").click();
  const requestResponse=await requested;
  expect(requestResponse.ok()).toBeTruthy();
  const createdRequest=await requestResponse.json();
  await expect(customerPage).toHaveURL(/\/events\//);
  const requirements=await request.put(`${api}/events/${createdRequest.event_id}/requirements`,{headers:{Authorization:`Bearer ${customer.token}`},data:{items:[{category_code:"host",role_label:"Ведущий",qty:1}]}});
  expect(requirements.ok()).toBeTruthy();
  await customerPage.reload();
  await expect(customerPage.getByRole("heading",{name:"Команда события",exact:true})).toBeVisible();
  await screens(customerPage,"event-request");
  await artistPage.goto(base+"/cabinet/performer");
  await artistPage.getByRole("button",{name:"Отправить предложение",exact:true}).click();
  await expect(artistPage).toHaveURL(/\/deals\//);
  const bookingId=artistPage.url().split("/deals/")[1].split(/[?#]/)[0];
  await artistPage.locator("button:visible").filter({hasText:/^Подтвердить условия$/}).first().click();
  await expect(artistPage.getByText("подтвердил только исполнитель",{exact:false}).first()).toBeVisible();
  await customerPage.goto(base+"/cabinet/customer");
  await expect(customerPage.locator(".cabinet-deal-card").first()).toContainText("Нужен ваш ответ");
  await expect(customerPage.locator(".cabinet-deal-card").first()).toContainText("Артист проверки");
  await expect(customerPage.getByRole("heading",{name:"Кого ещё нужно найти",exact:true})).toBeVisible();
  await customerPage.getByRole("link",{name:/Посмотреть предложение/}).click();
  await customerPage.locator("button:visible").filter({hasText:/^Подтвердить условия$/}).first().click();
  await customerPage.getByRole("tab",{name:"Чат",exact:true}).click();
  await customerPage.getByRole("textbox",{name:"Сообщение участникам сделки"}).fill("Проверка: выступление согласовано на выбранную дату.");
  await customerPage.locator(".chat-compose button").click();
  await artistPage.reload();
  await expect(artistPage.getByText("Проверка: выступление согласовано на выбранную дату.").first()).toBeVisible();
  await customerPage.locator("button:visible").filter({hasText:/^Удержать дату$/}).first().click();
  await expect(customerPage.getByText("Дата удерживается",{exact:true}).first()).toBeVisible();
  const customerRoom=await get(`/deal-room/${bookingId}`,customer.token),artistRoom=await get(`/deal-room/${bookingId}`,artist.token);
  for(const key of ["status","event_date","quote","hold","action_required_from","messages"])expect(customerRoom[key]).toEqual(artistRoom[key]);
  expect(customerRoom.status).toBe("DateHeld");
  expect(new Date(customerRoom.event_date).toISOString()).toBe(start.toISOString());
  expect(new Date(customerRoom.hold.expires_at).getTime()-Date.now()).toBeGreaterThan(23*3600000);
  await screens(customerPage,"deal");
  for(const [page,path,role] of [[customerPage,"/cabinet/customer","customer"],[artistPage,"/cabinet/performer","artist"]] as const){
    await page.goto(base+path);
    await expect(page.locator(".cabinet-deal-card").first()).toBeVisible();
    await page.setViewportSize({width:390,height:844});await noOverflow(page);
    await page.screenshot({path:info.outputPath(`${role}-mobile.png`),fullPage:true,animations:"disabled"});
    await screens(page,role+"-cabinet");
  }
  await customerPage.goto(base+"/briefs");
  const briefTitle=`Открытый заказ ${suffix}`;
  await customerPage.getByLabel("Название события",{exact:true}).fill(briefTitle);
  await customerPage.getByLabel("Начало события (МСК)",{exact:true}).fill(start.toISOString().slice(0,16));
  await customerPage.getByLabel("Окончание события (МСК)",{exact:true}).fill(end.toISOString().slice(0,16));
  const published=customerPage.waitForResponse(r=>r.url().endsWith("/briefs")&&r.request().method()==="POST");
  await customerPage.getByRole("button",{name:"Опубликовать",exact:true}).click();
  const brief=await (await published).json();
  await expect(customerPage.getByRole("status").filter({hasText:"Заказ опубликован"})).toBeVisible();
  await artistPage.goto(base+"/cabinet/performer");
  await expect(artistPage.getByRole("heading",{name:"Подходящие открытые заказы",exact:true})).toBeVisible();
  await artistPage.locator('a[href^="/briefs?q="]').filter({hasText:briefTitle}).click();
  await artistPage.getByLabel("Найти заказ",{exact:true}).fill(briefTitle);
  await artistPage.getByText("Откликнуться на заказ",{exact:true}).click();
  await artistPage.getByLabel("Ваше предложение",{exact:true}).fill("Моя программа подходит вашему событию.");
  await artistPage.getByRole("button",{name:"Отправить отклик",exact:true}).click();
  await expect(artistPage.getByText("Ваш отклик отправлен.",{exact:false})).toBeVisible();
  await customerPage.reload();
  await customerPage.getByLabel("Найти заказ",{exact:true}).fill(briefTitle);
  await customerPage.getByRole("button",{name:"Посмотреть отклики",exact:true}).click();
  await expect(customerPage.getByText("Моя программа подходит вашему событию.",{exact:true})).toBeVisible();
  await post(`/briefs/${brief.id}/close`,{},customer.token);
  await artistPage.reload();
  await artistPage.getByRole("button",{name:"Мои отклики",exact:true}).click();
  await expect(artistPage.getByText(briefTitle,{exact:true})).toBeVisible();
  await expect(artistPage.getByText("Закрыт",{exact:true})).toBeVisible();
  await noOverflow(customerPage);await noOverflow(artistPage);
  await customerContext.close();await artistContext.close();
});

test("регистрация выбирает правильный кабинет заказчика и артиста",async({browser})=>{
  for(const role of ["customer","artist"]){
    const ctx=await browser.newContext({viewport:{width:390,height:844}});
    const page=await ctx.newPage();
    const base=process.env.BOOKER_WEB_URL||"http://127.0.0.1:4316";
    await page.goto(`${base}/login?mode=register&role=${role}`);
    await expect(page.getByTestId(`role-option-${role}`)).toHaveAttribute("aria-pressed","true");
    await page.getByLabel("Имя",{exact:true}).fill(`Проверка ${role}`);
    await page.getByLabel("Email",{exact:true}).fill(`ui-${role}-${Date.now()}@booker.test`);
    await page.getByLabel("Пароль",{exact:true}).fill("Registration-test-2026");
    await page.locator('#accept_offer').check();
    await page.locator('#accept_privacy').check();
    await page.getByRole("button",{name:"Создать аккаунт",exact:true}).click();
    await expect(page).toHaveURL(new RegExp(`/cabinet/${role==="artist"?"performer":"customer"}`));
    await noOverflow(page);
    await ctx.close();
  }
});
