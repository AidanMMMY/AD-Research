#!/bin/bash
LOG=/tmp/indicator_progress.log
while true; do
  IND=$(docker exec alloyresearch-backend python -c "import redis; r=redis.from_url('redis://redis:6379/0'); print(r.llen('indicator'))")
  CNF=$(docker exec alloyresearch-backend python -c "import redis; r=redis.from_url('redis://redis:6379/0'); print(r.llen('cninfo'))")
  CEL=$(docker exec alloyresearch-backend python -c "import redis; r=redis.from_url('redis://redis:6379/0'); print(r.llen('celery'))")
  CNT=$(docker exec -i -e PGPASSWORD=$POSTGRES_PASSWORD alloyresearch-postgres psql -U etf -d ad_research -t -c "SELECT COUNT(*) FROM etf_indicator WHERE trade_date = '2026-07-15';")
  echo "$(date '+%Y-%m-%d %H:%M:%S') indicator=$IND cninfo=$CNF celery=$CEL etf_indicator_0715=$CNT" >> "$LOG"
  sleep 300
done
