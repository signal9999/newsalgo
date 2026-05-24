// pm2 ecosystem 設定ファイル
// 使い方:
//   pm2 start deploy/ecosystem.config.js
//   pm2 save && pm2 startup   # 自動起動設定

module.exports = {
  apps: [
    {
      name: "newsalgo-scheduler",
      script: "scheduler.py",
      interpreter: "python3",
      cwd: "/home/ubuntu/newsalgo",

      // 再起動設定
      autorestart: true,
      max_restarts: 10,
      restart_delay: 30000,   // 30秒待ってから再起動

      // ログ設定
      out_file: "./logs/pm2_out.log",
      error_file: "./logs/pm2_err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: true,

      // 環境変数（.env からも読み込まれる）
      env: {
        PYTHONUNBUFFERED: "1",
        TZ: "Asia/Tokyo",
      },

      // メモリ制限（超えたら自動再起動）
      max_memory_restart: "512M",

      // 単一インスタンス（複数起動防止）
      instances: 1,
      exec_mode: "fork",
    },
  ],
};
