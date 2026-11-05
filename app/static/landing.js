const plans = document.querySelector("#plans");
const planSelect = document.querySelector("#plan");
const form = document.querySelector("#lead-form");
const statusEl = document.querySelector("#lead-status");

function rub(value) {
  return new Intl.NumberFormat("ru-RU").format(value) + " ₽";
}

function addOption(id, label) {
  const option = document.createElement("option");
  option.value = id;
  option.textContent = label;
  planSelect.append(option);
}

function renderOffer(offer) {
  plans.replaceChildren();
  const subscription = document.createElement("article");
  subscription.className = "plan";
  const subTitle = document.createElement("h3");
  subTitle.textContent = offer.subscription.title;
  const subText = document.createElement("p");
  subText.textContent = offer.subscription.summary;
  const tiers = document.createElement("div");
  tiers.className = "tiers";
  for (const tier of offer.subscription.tiers) {
    const row = document.createElement("div");
    row.className = "tier";
    const name = document.createElement("b");
    name.textContent = tier.name;
    const price = document.createElement("b");
    price.textContent = rub(tier.price_rub);
    const detail = document.createElement("span");
    detail.textContent = tier.tryons.toLocaleString("ru-RU") + " примерок в месяц";
    const unit = document.createElement("span");
    unit.textContent = tier.per_tryon_rub + " ₽ за примерку в пакете";
    row.append(name, price, detail, unit);
    tiers.append(row);
    addOption(tier.id, "Подписка — " + tier.name);
  }
  const fine = document.createElement("p");
  fine.className = "fine";
  fine.textContent =
    "Сверх пакета " +
    rub(offer.subscription.extra_tryon_rub) +
    " за примерку. Неизрасходованные примерки в следующий месяц не переносятся.";
  subscription.append(subTitle, subText, tiers, fine);

  const commission = document.createElement("article");
  commission.className = "plan";
  const comTitle = document.createElement("h3");
  comTitle.textContent = offer.commission.title;
  const comText = document.createElement("p");
  comText.textContent = offer.commission.summary;
  const percent = document.createElement("p");
  percent.className = "commission-price";
  percent.textContent = offer.commission.percent + "%";
  const comFine = document.createElement("p");
  comFine.className = "fine";
  comFine.textContent =
    "Процент от оплаченного заказа, если покупатель сделал примерку и оплатил в течение " +
    offer.commission.window_hours +
    " часов. Примерка без покупки стоит 0 ₽. Магазин передаёт номер примерки вместе с заказом, иначе процент не начисляется.";
  commission.append(comTitle, comText, percent, comFine);

  plans.append(subscription, commission);
  addOption("commission", "Процент с покупки");
  addOption("undecided", "Пока не выбрали");
}

async function loadOffer() {
  const response = await fetch("/v1/offer");
  if (!response.ok) {
    plans.textContent = "Не удалось загрузить стоимость.";
    return;
  }
  renderOffer(await response.json());
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Отправляю…";
  const payload = Object.fromEntries(new FormData(form));
  const response = await fetch("/v1/leads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    statusEl.textContent = body.detail || "Заявку не приняли.";
    return;
  }
  form.reset();
  statusEl.textContent = "Заявка " + body.id + " принята. Мы ответим на указанный контакт.";
});

loadOffer().catch(() => {
  plans.textContent = "Не удалось загрузить стоимость.";
});
