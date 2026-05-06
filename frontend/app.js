const API_BASE_URL = 'http://127.0.0.1:8000'; // Ensure this matches your backend port
let token = localStorage.getItem('jwt_token');

let allNotes = [];
let editingNoteId = null; 

const authSection = document.getElementById('auth-section');
const dashboardSection = document.getElementById('dashboard-section');
const notesList = document.getElementById('notes-list');
const authMessage = document.getElementById('auth-message');

function init() {
    if (token) {
        showDashboard();
        fetchNotes();
    } else {
        showAuth();
    }
}

function showAuth() {
    authSection.classList.remove('hidden');
    dashboardSection.classList.add('hidden');
}

function showDashboard() {
    authSection.classList.add('hidden');
    dashboardSection.classList.remove('hidden');
}

// register
document.getElementById('register-btn').addEventListener('click', async () => {
    const u = document.getElementById('username').value;
    const p = document.getElementById('password').value;
    const r = document.getElementById('role-select').value;
    
    try {
        const res = await fetch(`${API_BASE_URL}/api/v1/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, password: p, role: r }) 
        });
        if (res.ok) {
            authMessage.style.color = 'green';
            authMessage.innerText = "Registration successful! Please login.";
        } else {
            const data = await res.json();
            authMessage.innerText = data.detail || "Registration failed.";
        }
    } catch (err) { console.error("API Error:", err); }
});

// login
document.getElementById('login-btn').addEventListener('click', async () => {
    const u = document.getElementById('username').value;
    const p = document.getElementById('password').value;
    
    const formData = new URLSearchParams();
    formData.append('username', u);
    formData.append('password', p);

    try {
        const res = await fetch(`${API_BASE_URL}/token`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/x-www-form-urlencoded' 
            },
            body: formData
        });
        
        if (res.ok) {
            const data = await res.json();
            token = data.access_token;
            localStorage.setItem('jwt_token', token); 
            authMessage.innerText = "";
            init(); 
        } else {
            authMessage.innerText = "Invalid credentials.";
        }
    } catch (err) { console.error("API Error:", err); }
});

//Fetch Notes 
async function fetchNotes() {
    try {
        const res = await fetch(`${API_BASE_URL}/api/v1/notes`, {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${token}` } 
        });
        
        if (res.ok) {
            allNotes = await res.json(); 
            renderNotes(allNotes);
        } else if (res.status === 401) {
            logout(); 
        }
    } catch (err) { console.error("API Error:", err); }
}

// C & U notes
document.getElementById('add-note-btn').addEventListener('click', async () => {
    const title = document.getElementById('note-title').value;
    const content = document.getElementById('note-content').value;
    
    if (!title) return alert("Title is required");


    const method = editingNoteId ? 'PUT' : 'POST';
    const url = editingNoteId 
        ? `${API_BASE_URL}/api/v1/notes/${editingNoteId}` 
        : `${API_BASE_URL}/api/v1/notes`;

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify({ title, content })
        });
        
        if (res.ok) {
            document.getElementById('note-title').value = '';
            document.getElementById('note-content').value = '';
            
            document.getElementById('add-note-btn').innerText = 'Save Note';
            editingNoteId = null; 
            
            fetchNotes(); // Refresh list
        }
    } catch (err) { console.error("API Error:", err); }
});

// notes D & E
window.editNote = (id) => {
    const note = allNotes.find(n => n.id === id);
    if (note) {
        document.getElementById('note-title').value = note.title;
        document.getElementById('note-content').value = note.content;
        
        document.getElementById('add-note-btn').innerText = 'Update Note';
        editingNoteId = id;
        
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
};

window.deleteNote = async (id) => {
    if (!confirm("Are you sure you want to delete this note?")) return;
    
    try {
        const res = await fetch(`${API_BASE_URL}/api/v1/notes/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (res.ok) {
            fetchNotes(); 
        }
    } catch (err) { console.error("API Error:", err); }
};

//logout
document.getElementById('logout-btn').addEventListener('click', logout);

function logout() {
    token = null;
    localStorage.removeItem('jwt_token');
    showAuth();
}

// render
function renderNotes(notes) {
    if (notes.length === 0) {
        notesList.innerHTML = "<p>No notes found. Create one above!</p>";
        return;
    }
    
    // Inject the note ID directly into the onclick handlers for the buttons
    notesList.innerHTML = notes.map(note => `
        <div class="note-item" style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div class="note-content-wrapper" style="flex-grow: 1; padding-right: 15px;">
                <h4>${note.title}</h4>
                <p>${note.content}</p>
            </div>
            <div class="note-actions" style="display: flex; flex-direction: column; gap: 8px; min-width: 80px;">
                <button onclick="editNote(${note.id})" class="edit-btn" style="background: #28a745; padding: 6px 10px; font-size: 0.85em; width: 100%; border: none; color: white; border-radius: 4px; cursor: pointer;">Edit</button>
                <button onclick="deleteNote(${note.id})" class="danger delete-btn" style="background: #dc3545; padding: 6px 10px; font-size: 0.85em; width: 100%; border: none; color: white; border-radius: 4px; cursor: pointer;">Delete</button>
            </div>
        </div>
    `).reverse().join(''); // Reverse to show newest first
}
//decode
function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(c => 
            '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
        ).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) { return null; }
}

// --- Admin Functionality ---
document.getElementById('fetch-users-btn').addEventListener('click', async () => {
    try {
        const res = await fetch(`${API_BASE_URL}/api/v1/admin/all-users`, {
            method: 'GET',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const usersListDiv = document.getElementById('users-list');
        if (res.ok) {
            const users = await res.json();
            usersListDiv.innerHTML = users.map(u => 
                `<div style="padding: 5px; border-bottom: 1px solid #ddd;">
                    <strong>ID:</strong> ${u.id} | 
                    <strong>User:</strong> ${u.username} | 
                    <strong>Role:</strong> <span style="color: ${u.role === 'admin' ? 'red' : 'black'}">${u.role}</span>
                </div>`
            ).join('');
        } else {
            usersListDiv.innerHTML = `<p style="color: red;">Error: You do not have permission to view this.</p>`;
        }
    } catch (err) { console.error("API Error:", err); }
});

// --- Initialization ---
function init() {
    if (token) {
        showDashboard();
        fetchNotes();
        
        // NEW: Check role to reveal Admin Panel
        const decodedToken = parseJwt(token);
        if (decodedToken && decodedToken.role === 'admin') {
            document.getElementById('admin-panel').classList.remove('hidden');
        } else {
            document.getElementById('admin-panel').classList.add('hidden');
        }
    } else {
        showAuth();
    }
}
