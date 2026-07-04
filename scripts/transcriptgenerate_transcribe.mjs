#!/usr/bin/env node
import crypto from "node:crypto";

const API_BASE = "https://www.transcriptgenerate.com/prod-api";
const KEY = Buffer.from("aaDJL2d9DfhLZO0z", "utf8");
const IV = Buffer.from("412ADDSSFA342442", "utf8");

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) continue;
    const key = arg.slice(2);
    if (key === "json") {
      args.json = true;
    } else {
      args[key] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function zeroPad(buf) {
  const rem = buf.length % 16;
  return rem === 0 ? buf : Buffer.concat([buf, Buffer.alloc(16 - rem)]);
}

function zeroUnpad(buf) {
  let end = buf.length;
  while (end > 0 && buf[end - 1] === 0) end -= 1;
  return buf.subarray(0, end);
}

function encryptPayload(payload) {
  const text = typeof payload === "string" ? payload : JSON.stringify(payload);
  const cipher = crypto.createCipheriv("aes-128-cbc", KEY, IV);
  cipher.setAutoPadding(false);
  return Buffer.concat([
    cipher.update(zeroPad(Buffer.from(text, "utf8"))),
    cipher.final(),
  ]).toString("base64");
}

function decryptPayload(cipherText) {
  const decipher = crypto.createDecipheriv("aes-128-cbc", KEY, IV);
  decipher.setAutoPadding(false);
  const plain = zeroUnpad(
    Buffer.concat([
      decipher.update(Buffer.from(cipherText, "base64")),
      decipher.final(),
    ]),
  ).toString("utf8");
  try {
    return JSON.parse(plain);
  } catch {
    return plain;
  }
}

async function apiRequest(path, { method = "GET", token, body, params, retries = 3 } = {}) {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, value);
    }
  }

  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json, text/plain, */*",
    Origin: "https://www.transcriptgenerate.com",
    Referer: "https://www.transcriptgenerate.com/zh-CN",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const fetchOptions = { method, headers };
  if (body) {
    fetchOptions.body = JSON.stringify(encryptPayload(body));
  }

  let lastError;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(url.toString(), fetchOptions);
      const raw = await res.text();
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${raw.slice(0, 200)}`);
      }
      const maybeJson = JSON.parse(raw);
      return typeof maybeJson === "string" ? decryptPayload(maybeJson) : maybeJson;
    } catch (err) {
      lastError = err;
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, 1000 * attempt));
      }
    }
  }
  throw lastError;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url;
  const email = args.email || process.env.TG_EMAIL;
  const password = args.password || process.env.TG_PASSWORD;
  const targetLanguage = args["target-language"] || "auto";
  const resumeTaskId = args["task-id"];  // resume mode: skip createTask, poll existing task

  if (!email || !password) throw new Error("Missing --email/--password or TG_EMAIL/TG_PASSWORD");

  const login = await apiRequest("/login", {
    method: "POST",
    body: {
      type: 2,
      username: email,
      password,
      appType: "transcript",
      appClient: "web",
    },
  });
  if (login.code !== 200 || !login.token) {
    throw new Error(`Login failed: ${login.msg || JSON.stringify(login)}`);
  }

  let task;
  if (resumeTaskId) {
    // Resume mode: query existing task, don't create a new one
    if (!url) throw new Error("Missing --url (needed for output metadata)");
    const queried = await apiRequest("/transcript/queryTask", {
      token: login.token,
      params: { taskId: resumeTaskId },
    });
    if (queried.code !== 200) throw new Error(`Query failed: ${queried.msg || JSON.stringify(queried)}`);
    task = { code: 200, data: queried.data };
  } else {
    if (!url) throw new Error("Missing --url");
    task = await apiRequest("/transcript/createTask", {
      method: "POST",
      token: login.token,
      retries: 1,  // NEVER retry: duplicate tasks = duplicate charges
      body: {
        appType: "transcript",
        workUrl: url,
        type: "text",
        targetLanguage,
      },
    });
  }
  if (task.code !== 200 || !task.data?.taskId) {
    throw new Error(`Create task failed: ${task.msg || JSON.stringify(task)}`);
  }

  let data = task.data;
  for (let i = 0; data.status === "WAITING" && i < 900; i += 1) {
    await sleep(2000);
    const queried = await apiRequest("/transcript/queryTask", {
      token: login.token,
      params: { taskId: data.taskId },
    });
    if (queried.code !== 200) throw new Error(`Query failed: ${queried.msg || JSON.stringify(queried)}`);
    data = queried.data;
  }

  const output = {
    code: task.code,
    msg: task.msg,
    taskId: data.taskId || task.data.taskId,
    status: data.status,
    title: data.title || "",
    content: data.content || "",
    textContent: data.textContent || "",
    platform: data.platform || "",
    duration: data.duration || 0,
    workUrl: data.workUrl || url,
  };

  if (args.json) {
    console.log(JSON.stringify(output, null, 2));
  } else {
    console.log(`# ${output.title || "Transcript"}`);
    console.log("");
    console.log(`status: ${output.status}`);
    console.log(`taskId: ${output.taskId}`);
    if (output.platform) console.log(`platform: ${output.platform}`);
    if (output.duration) console.log(`duration: ${output.duration}`);
    console.log("");
    console.log(output.textContent || "(empty transcript)");
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
