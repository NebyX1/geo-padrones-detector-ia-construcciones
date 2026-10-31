import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir:'./e2e',fullyParallel:false,workers:1,retries:0,
  use:{baseURL:process.env.E2E_BASE_URL||'http://127.0.0.1:5173',actionTimeout:15000,browserName:'chromium',channel:'msedge',headless:true,viewport:{width:1536,height:1080},screenshot:'only-on-failure',trace:'retain-on-failure'},
  reporter:[['list'],['junit',{outputFile:'../artifacts/tests/e2e.xml'}]],
})
