#!/usr/bin/env bash
# teacherctl.sh start|stop — the corpus teacher server, tracked by a PID file (no pattern matching).
cd ~/cin-minai/repo-train
case $1 in
  start) setsid -f bash -c 'echo $$ > teacher.pid; exec ./teacher.sh' > teacher.log 2>&1 < /dev/null
         for i in $(seq 120); do curl -sf http://127.0.0.1:18091/health >/dev/null && break; sleep 1; done
         curl -s http://127.0.0.1:18091/health; echo
         nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader ;;
  stop)  [ -f teacher.pid ] && kill "$(cat teacher.pid)" 2>/dev/null; rm -f teacher.pid; sleep 3; echo stopped ;;
esac
