import http from 'k6/http';
import { check } from 'k6';

// Arrival-rate executor: `target` is requests-per-second, not VUs. (With a VU ramp and sleep(0.1),
// 2,000 VUs would be ~20k rps, not the 2k the plan calls for.)
export const options = {
  scenarios: {
    last_hour_spike: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 3000,
      stages: [
        { duration: '30s', target: 50 },    // Warmup: steady 50 rps
        { duration: '2m', target: 500 },    // Spike ramp up
        { duration: '2m', target: 2000 },   // Peak spike (2,000 rps)
        { duration: '30s', target: 0 },     // Ramp down
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],     // Under 5% error rate allowed under extreme spike
    http_req_duration: ['p(95)<300'],   // 95% of requests under 300ms
  },
};

// 409 (already voted) is a correct answer once the 10k pool is drained, not a failure.
http.setResponseCallback(http.expectedStatuses(200, 409));

const BASE_URL = __ENV.API_URL || 'http://localhost:8080';
const HEADERS = { headers: { 'Content-Type': 'application/json' } };

export default function () {
  // Synthetic student ID between 1 and 10000
  const studentId = `STU${String(Math.floor(Math.random() * 10000) + 1).padStart(5, '0')}`;

  const verifyRes = http.post(`${BASE_URL}/eligibility/verify`, JSON.stringify({ student_id: studentId }), HEADERS);
  check(verifyRes, { 'verify 200 or 409': (r) => r.status === 200 || r.status === 409 });
  if (verifyRes.status !== 200) return;

  const voteRes = http.post(
    `${BASE_URL}/vote`,
    JSON.stringify({ token: verifyRes.json('token'), candidate_id: 'Slate 2: Tech & Innovation League' }),
    HEADERS
  );
  check(voteRes, { 'vote queued (200)': (r) => r.status === 200 });
}
