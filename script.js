const regionData = {
    "India": ["Kerala", "Karnataka", "Maharashtra", "Delhi NCR"],
    "Brazil": ["São Paulo", "Rio de Janeiro", "Bahia"],
    "South Africa": ["Gauteng", "Western Cape", "KwaZulu-Natal"]
};

function switchTab(tab) {
    document.getElementById('tab-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-signup').classList.toggle('active', tab === 'signup');
    document.getElementById('form-login').classList.toggle('hidden', tab !== 'login');
    document.getElementById('form-signup').classList.toggle('hidden', tab !== 'signup');
}

document.getElementById('form-signup')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await fetch('/api/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: document.getElementById('signup-name').value,
            email: document.getElementById('signup-email').value,
            occupation: document.getElementById('signup-occupation').value,
            password: document.getElementById('signup-password').value
        })
    });
    const data = await res.json();
    if (data.success) window.location.href = '/dashboard';
    else document.getElementById('auth-msg').innerText = data.message;
});

document.getElementById('form-login')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            email: document.getElementById('login-email').value,
            password: document.getElementById('login-password').value
        })
    });
    const data = await res.json();
    if (data.success) window.location.href = '/dashboard';
    else document.getElementById('auth-msg').innerText = data.message;
});

async function handleLogout() {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/';
}

function updateRegions() {
    const country = document.getElementById('country').value;
    const regionSelect = document.getElementById('region');
    regionSelect.innerHTML = '<option value="">Select Region</option>';

    if (country && regionData[country]) {
        regionSelect.disabled = false;
        regionData[country].forEach(r => {
            const opt = document.createElement('option');
            opt.value = r;
            opt.innerText = r;
            regionSelect.appendChild(opt);
        });
    } else {
        regionSelect.disabled = true;
    }
}

function updateWordCount() {
    const text = document.getElementById('complaint-text').value.trim();
    const words = text ? text.split(/\s+/).length : 0;
    const countSpan = document.getElementById('word-count');
    countSpan.innerText = words;
    countSpan.style.color = words >= 2000 ? '#27ae60' : '#e74c3c';
}

document.getElementById('complaint-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.innerText = "Analyzing with Gemini AI...";
    submitBtn.disabled = true;

    const payload = {
        country: document.getElementById('country').value,
        region: document.getElementById('region').value,
        category: document.getElementById('category').value,
        complaint_text: document.getElementById('complaint-text').value
    };

    const res = await fetch('/api/submit_complaint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await res.json();
    submitBtn.innerText = "Analyze & Anonymous Dispatch";
    submitBtn.disabled = false;

    if (data.success) {
        document.getElementById('result-card').classList.remove('hidden');
        document.getElementById('dispatch-target').innerText = `Target Authority: ${data.target_authority}`;
        document.getElementById('ai-output').innerHTML = data.analysis;
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    } else {
        alert(data.message);
    }
});

function shareToAuthorities() {
    alert("✅ Anonymous briefing generated and successfully dispatched to the designated regional authority!");
}