const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const app = express();

app.use(express.json());
app.use(cors());

// --- DATABASE CONNECTION ---
// Alexsco: This connects to your specific MongoDB cluster
const mongoURI = "mongodb+srv://BinaryOption:Alex4krist@cluster0.zgguzis.mongodb.net/TradingData?retryWrites=true&w=majority&appName=Cluster0";

mongoose.connect(mongoURI)
    .then(() => console.log("✅ Cloud Database Connected: TradingData"))
    .catch(err => console.error("❌ Database Connection Error:", err));

// --- USER SCHEMA ---
const userSchema = new mongoose.Schema({
    name: { type: String, required: true },
    email: { type: String, unique: true, required: true },
    password: { type: String, required: true },
    balance: { type: Number, default: 0.00 }, 
    isVerified: { type: Boolean, default: false },
    createdAt: { type: Date, default: Date.now }
});

const User = mongoose.model('User', userSchema);

// --- ROUTES ---

// 1. Status Route (Turns the light GREEN on your website)
app.get('/status', (req, res) => {
    res.json({ success: true, status: "online" });
});

// 2. Home Route
app.get('/', (req, res) => {
    res.send("BinaryOption Terminal API is Running...");
});

// Registration Route
app.post('/register', async (req, res) => {
    try {
        const { name, email, password } = req.body;
        const existingUser = await User.findOne({ email });
        if (existingUser) return res.status(400).json({ message: "Email already in use" });

        const newUser = new User({ name, email, password });
        await newUser.save();
        res.status(201).json({ 
            success: true, 
            user: { name: newUser.name, email: newUser.email, balance: newUser.balance } 
        });
    } catch (error) {
        res.status(500).json({ message: "Error creating account" });
    }
});

// Login Route
app.post('/login', async (req, res) => {
    try {
        const { email, password } = req.body;
        const user = await User.findOne({ email, password });
        if (user) {
            res.json({ 
                success: true, 
                user: { name: user.name, email: user.email, balance: user.balance } 
            });
        } else {
            res.status(401).json({ success: false, message: "Invalid credentials" });
        }
    } catch (error) {
        res.status(500).json({ message: "Login error" });
    }
});

// Withdrawal Request
app.post('/withdraw', (req, res) => {
    const { email, amount, wallet } = req.body;
    console.log(`💰 WITHDRAWAL: ${email} requested $${amount} to ${wallet}`);
    res.json({ success: true, message: "Withdrawal request submitted." });
});

// --- SERVER START ---
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 Server active on port ${PORT}`));
