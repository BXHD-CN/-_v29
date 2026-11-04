/* 涉外急诊语言服务台 · 云服务公开配置
 * 来源：workbuddy_cloud_service(activate) 返回的 publicConfig。
 * 这里只包含「端用户可见」的公开值，可随前端代码发布；
 * 底层 environment id 与所有 provider 密钥都留在服务端，绝不写入本文件。
 * 注意：endpoint / publishableKey / oauthRelayBaseUrl 只能取自这里，
 * 不要从 location、env 或任何 BFF 推导，也不要硬编码其它域名。
 */
"use strict";
window.WB_PUBLIC_CONFIG = {
  resourceId: "wbcs_cewcYHJ85qJeJQGfQ21tjx",
  endpoint: "https://er-lang-service-desk.app.workbuddy.host",
  oauthRelayBaseUrl: "https://www.workbuddy.cn/v2/as/genie-baas/oauth",
  publishableKey: "wbpk_xp3kbiaDkp2BQ4HnqFvZbl_Ko7ISTzWjqpuyLhBpy1u6kWRnKtuToHu"
};
