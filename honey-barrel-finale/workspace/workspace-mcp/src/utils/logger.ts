type LogLevel = "debug" | "info" | "warn" | "error";

const LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const CURRENT_LEVEL: LogLevel =
  (process.env.LOG_LEVEL as LogLevel) || "info";

function shouldLog(level: LogLevel) {
  return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[CURRENT_LEVEL];
}

function timestamp() {
  return new Date().toISOString();
}

function format(level: LogLevel, message: string, meta?: any) {
  const base = `[${timestamp()}] [${level.toUpperCase()}] ${message}`;
  if (meta) {
    return `${base} ${JSON.stringify(meta)}`;
  }
  return base;
}

export const logger = {
  debug: (msg: string, meta?: any) => {
    if (shouldLog("debug")) console.log(format("debug", msg, meta));
  },

  info: (msg: string, meta?: any) => {
    if (shouldLog("info")) console.log(format("info", msg, meta));
  },

  warn: (msg: string, meta?: any) => {
    if (shouldLog("warn")) console.warn(format("warn", msg, meta));
  },

  error: (msg: string, meta?: any) => {
    if (shouldLog("error")) console.error(format("error", msg, meta));
  },
};
