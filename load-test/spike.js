import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 },    // Warmup: steady 50 RPS
    { duration: '2m', target: 500 },    // Spike ramp up
    { duration: '2m', target: 2000 },   // Peak spike (2,000 RPS)
    { duration: '30s', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],     // Under 5% error rate allowed under extreme spike
    http_req_duration: ['p(95)<300'],   // 95% of requests under 300ms
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8080';

export default function () {
  // Generate synthetic student ID between 1 and 10000
  const randomStudentNum = Math.floor(Math.random() * 10000) + 1;
  const studentId = `STU${String(randomStudentNum).padStart(5, '0')}`;

  // 1. Verify eligibility
  const verifyRes = http.post(
    `${BASE_URL}/eligibility/verify`,
    JSON.stringify({ student_id: studentId }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  const isEligible = check(verifyRes, {
    'verify status 200 or 409': (r) => r.status === 200 || r.status === 409,
  });

  if (verifyRes.status === 200) {
    const data = JSON.parse(verifyRes.body);
    const token = data.token;

    // 2. Submit ballot vote
    const candidateChoice = 'Slate 2: Tech & Innovation League';
    const voteRes = http.post(
      `${BASE_URL}/vote`,
      JSON.stringify({ token: token, candidate_id: candidateChoice }),
      { headers: { 'Content-Type': 'application/json' } }
    );

    check(voteRes, {
      'vote queued (200)': (r) => r.status === 200,
    });
  }

  sleep(0.1);
}
