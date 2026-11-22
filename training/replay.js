/* Synthetic classroom state. Every transition only changes this browser session. */
(() => {
  "use strict";

  const packetPoints = 3;
  const purchaseItem = "纸舟课堂练习册";
  const purchasePoints = 4;
  const examplePermissionPoints = 20;
  const points = (count) => count + " 课堂点";
  const field = (label, value) => ({ label, value });

  const routes = new Map([
    ["gift", {
      name: "纸舟课堂 · 红包练习",
      steps: ["gift-message", "gift-balance", "gift-withdrawal", "gift-allowance"],
      initial: { balance: 0, withdrawal: null },
      screens: [
        ({ balance }) => ({
          title: "教学红包卡片",
          description: "领取后，课堂页面会把练习点记入本次演练的显示余额。",
          status: "待领取",
          rows: [field("卡片金额", points(packetPoints)), field("页面显示余额", points(balance))]
        }),
        ({ balance }) => ({
          title: "教学红包领取结果",
          description: "这一步改变的是课堂页面内的数字。核对到账还需要资金侧流水。",
          status: "课堂点已计入",
          rows: [field("领取记录", "+" + points(packetPoints)), field("页面显示余额", points(balance))],
          tone: "notice"
        }),
        ({ balance }) => ({
          title: "教学余额页",
          description: "切到余额页后，看到同一场演练中刚记录的课堂点数。",
          status: "页面余额已显示",
          rows: [field("页面显示余额", points(balance)), field("独立到账记录", "待核")],
          tone: "notice"
        }),
        ({ withdrawal, balance }) => ({
          title: "教学提现申请",
          description: "课堂流程停在绑定提示处。实际钱包要求做什么，需要看原始请求。",
          status: "申请停在绑定提示",
          rows: [
            field("课堂提现申请", points(withdrawal)),
            field("剩余页面显示余额", points(balance)),
            field("实际钱包请求", "待核")
          ],
          tone: "blocked"
        }),
        ({ withdrawal }) => ({
          title: "教学授权提示对照",
          description: "申请金额和权限范围是两类信息。这里的权限额度是用来练习辨认的课堂假设。",
          status: "实际授权待核",
          rows: [
            field("回看课堂提现申请", points(withdrawal)),
            field("课堂假设权限额度", points(examplePermissionPoints)),
            field("实际签名或转出记录", "待核")
          ],
          tone: "blocked"
        })
      ]
    }],
    ["shop", {
      name: "纸舟课堂 · 商铺练习",
      steps: ["shop-order", "shop-link", "shop-payment", "shop-payment-or-allowance"],
      initial: { order: null, paymentRequest: null },
      screens: [
        () => ({
          title: "教学商品详情",
          description: "提交后生成一张课堂订单，并记录订单金额和待付款状态。",
          status: "订单未生成",
          rows: [field("虚构商品", purchaseItem), field("示例价格", points(purchasePoints))]
        }),
        ({ order }) => ({
          title: "教学订单详情",
          description: "订单卡出现后，买家能看到编号、金额和待付款状态。原始发送方需另行核验。",
          status: "订单待付款",
          rows: [
            field("虚构商品", order.item),
            field("虚构订单", order.id),
            field("订单金额", points(order.amount)),
            field("原始发送方", "待核")
          ],
          tone: "notice"
        }),
        ({ order }) => ({
          title: "教学外链确认",
          description: "记录从聊天界面前往外部页面的提示。本地演练停在这一步，供学员核对商家与收银页面的关系。",
          status: "外部页面归属待核",
          rows: [field("关联虚构订单", order.id), field("页面边界", "聊天界面 → 外部页面（课堂示例）")],
          tone: "blocked"
        }),
        ({ paymentRequest }) => ({
          title: "教学收银台",
          description: "收银请求沿用刚才的课堂订单金额。出现应付金额后，订单仍处于待付款状态。",
          status: "已显示付款请求",
          rows: [
            field("关联虚构订单", paymentRequest.orderId),
            field("应付金额", points(paymentRequest.amount)),
            field("付款倒计时", "课堂时钟已暂停"),
            field("资金侧付款回执", "待核")
          ],
          tone: "notice"
        }),
        ({ paymentRequest }) => ({
          title: "教学付款与授权核对",
          description: "付款请求涉及本单应付，权限提示涉及可用额度。课堂对照值用来练习区分两者。",
          status: "订单待付款，实际授权待核",
          rows: [
            field("本单应付", points(paymentRequest.amount)),
            field("课堂假设权限额度", points(examplePermissionPoints)),
            field("实际付款或权限回执", "待核")
          ],
          tone: "blocked"
        })
      ]
    }]
  ]);

  function routeFor(lessonId) {
    const route = routes.get(lessonId);
    if (!route) throw new Error("Unsupported classroom route");
    return route;
  }

  function start(lessonId) {
    return Object.freeze({ lessonId, completed: 0, ...routeFor(lessonId).initial });
  }

  function advance(state, stepId) {
    const route = routeFor(state.lessonId);
    if (!stepId || route.steps[state.completed] !== stepId) {
      throw new Error("Classroom operations must run once and in order");
    }
    const next = { ...state, completed: state.completed + 1 };
    switch (stepId) {
      case "gift-message":
        next.balance += packetPoints;
        break;
      case "gift-withdrawal":
        next.withdrawal = state.balance;
        break;
      case "shop-order":
        next.order = Object.freeze({ id: "ZZ-001", item: purchaseItem, amount: purchasePoints });
        break;
      case "shop-payment":
        next.paymentRequest = Object.freeze({ orderId: state.order.id, amount: state.order.amount });
        break;
    }
    return Object.freeze(next);
  }

  function view(state) {
    const route = routeFor(state.lessonId);
    return { name: route.name, tone: "neutral", ...route.screens[state.completed](state) };
  }

  window.trainingReplay = Object.freeze({ start, advance, view });
})();
