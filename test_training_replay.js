"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = { window: {} };
vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, "training", "replay.js"), "utf8"),
  context
);
const { start, advance, view } = context.window.trainingReplay;

function fields(state) {
  return Object.fromEntries(view(state).rows.map(({ label, value }) => [label, value]));
}

test("claim updates the display balance once, then the withdrawal stops at a prompt", () => {
  const initial = start("gift");
  assert.equal(fields(initial)["页面显示余额"], "0 课堂点");
  assert.throws(() => advance(initial, "gift-balance"), /in order/);

  const claimed = advance(initial, "gift-message");
  assert.throws(() => advance(claimed, "gift-message"), /in order/);
  assert.equal(fields(initial)["页面显示余额"], "0 课堂点");
  assert.equal(fields(claimed)["页面显示余额"], "3 课堂点");

  const balanceShown = advance(claimed, "gift-balance");
  const withdrawal = advance(balanceShown, "gift-withdrawal");
  assert.equal(fields(balanceShown)["页面显示余额"], "3 课堂点");
  assert.equal(fields(withdrawal)["课堂提现申请"], "3 课堂点");
  assert.equal(fields(withdrawal)["剩余页面显示余额"], "3 课堂点");
  assert.equal(view(withdrawal).tone, "blocked");

  const compared = advance(withdrawal, "gift-allowance");
  assert.equal(fields(compared)["课堂假设权限额度"], "20 课堂点");
  assert.equal(fields(compared)["实际签名或转出记录"], "待核");
  assert.equal(fields(start("gift"))["页面显示余额"], "0 课堂点");
});

test("the cashier carries the pending classroom order forward without settling it", () => {
  const initial = start("shop");
  assert.equal(view(initial).status, "订单未生成");
  assert.throws(() => advance(initial, "shop-payment"), /in order/);

  const ordered = advance(initial, "shop-order");
  const prompt = advance(ordered, "shop-link");
  const cashier = advance(prompt, "shop-payment");
  const compared = advance(cashier, "shop-payment-or-allowance");

  assert.equal(fields(ordered)["虚构订单"], "ZZ-001");
  assert.equal(fields(prompt)["关联虚构订单"], fields(ordered)["虚构订单"]);
  assert.equal(fields(cashier)["关联虚构订单"], fields(ordered)["虚构订单"]);
  assert.equal(fields(cashier)["应付金额"], fields(ordered)["订单金额"]);
  assert.equal(fields(cashier)["付款倒计时"], "课堂时钟已暂停");
  assert.equal(fields(compared)["本单应付"], "4 课堂点");
  assert.equal(fields(compared)["课堂假设权限额度"], "20 课堂点");
  assert.equal(view(compared).status, "订单待付款，实际授权待核");
  assert.equal(view(ordered).status, "订单待付款");
  assert.throws(() => advance(compared, "shop-order"), /in order/);
});
