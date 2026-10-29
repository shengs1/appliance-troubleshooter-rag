// public/custom.js
// Custom JavaScript for Trợ lý sự cố điện gia dụng (Appliance Troubleshooting Chatbot)

(function () {
    console.log("Trợ lý sự cố điện gia dụng - Frontend initialized.");

    let currentUserChecked = false;
    let currentUserRole = null;

    // 1. Chặn hoàn toàn việc kéo thả file vào trình duyệt (Disable File Upload completely)
    window.addEventListener("dragover", function (e) {
        if (e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes("Files")) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "none";
        }
    }, false);

    window.addEventListener("drop", function (e) {
        if (e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes("Files")) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, false);

    // 2. Tinh chỉnh giao diện trang đăng nhập (DHV Branding, Single Column, Việt hóa)
    function enhanceLoginPage() {
        const form = document.querySelector("form");
        if (!form) return;

        // Xác nhận đây là form login dựa trên input email/password
        const emailInput = form.querySelector('input#email, input[name="email"]');
        const passwordInput = form.querySelector('input#password, input[name="password"]');
        if (!emailInput || !passwordInput) return;

        const formWrapper = form.parentElement;
        if (!formWrapper) return;

        // 1. Chèn Header thương hiệu DHV trên đầu form
        const existingHeader = document.getElementById("dhv-login-header");
        if (!existingHeader || existingHeader.parentElement !== formWrapper) {
            if (existingHeader) existingHeader.remove();

            const headerEl = document.createElement("div");
            headerEl.id = "dhv-login-header";
            headerEl.className = "dhv-login-header";
            headerEl.innerHTML = `
                <div class="dhv-login-logo-wrap">
                    <img src="/public/branding/dhv-logo.png" alt="DHV Logo" class="dhv-login-logo"
                         onerror="this.style.display='none'; document.getElementById('dhv-login-fallback').style.display='flex';" />
                    <div id="dhv-login-fallback" class="dhv-login-fallback" style="display: none;">🛠️</div>
                </div>
                <h2 class="dhv-login-title">Trợ lý sự cố điện gia dụng</h2>
                <p class="dhv-login-subtitle">Đăng nhập để tra cứu mã lỗi và khắc phục sự cố</p>
            `;
            formWrapper.insertBefore(headerEl, form);
        }

        // 2. Việt hóa các chuỗi tiếng Anh mặc định
        const h1 = form.querySelector("h1");
        if (h1 && (h1.innerText.includes("Login") || h1.innerText.includes("access the app"))) {
            h1.innerText = "Đăng nhập";
        }

        const emailLabel = form.querySelector('label[for="email"]');
        if (emailLabel && emailLabel.innerText.trim() === "Email address") {
            emailLabel.innerText = "Email";
        }

        const passwordLabel = form.querySelector('label[for="password"]');
        if (passwordLabel && passwordLabel.innerText.trim() === "Password") {
            passwordLabel.innerText = "Mật khẩu";
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn && (submitBtn.innerText.includes("Sign In") || submitBtn.innerText.includes("Continue"))) {
            submitBtn.innerText = "Đăng nhập";
        }

        if (emailInput && emailInput.placeholder === "me@example.com") {
            emailInput.placeholder = "Nhập email của bạn";
        }

        // 3. Chèn Footer chứa link Quên mật khẩu và Đăng ký
        const existingFooter = document.getElementById("dhv-login-footer");
        if (!existingFooter || existingFooter.parentElement !== form) {
            if (existingFooter) existingFooter.remove();

            const footerEl = document.createElement("div");
            footerEl.id = "dhv-login-footer";
            footerEl.className = "dhv-login-footer";
            footerEl.innerHTML = `
                <a href="/public/forgot-password.html" class="dhv-forgot-link">Quên mật khẩu?</a>
                <div class="dhv-register-wrap">
                    Chưa có tài khoản? <a href="/public/register.html" class="dhv-register-link">Đăng ký tài khoản</a>
                </div>
            `;
            form.appendChild(footerEl);
        }
    }

    // 3. Tinh chỉnh Chat Composer (Placeholder tiếng Việt & chặn upload file)
    function enhanceComposer() {
        const textareas = document.querySelectorAll("textarea");
        textareas.forEach(function (ta) {
            if (!ta.placeholder || ta.placeholder.includes("Type your message") || ta.placeholder.includes("Type a message")) {
                ta.placeholder = "Nhập câu hỏi của bạn...";
            }
        });

        // Ẩn mọi nút upload hoặc attach file nếu còn sót lại trong DOM
        const uploadButtons = document.querySelectorAll(
            'button[aria-label*="upload" i], button[aria-label*="attach" i], button#upload-button, div[data-testid*="upload"]'
        );
        uploadButtons.forEach(function (btn) {
            btn.style.display = "none";
            btn.setAttribute("disabled", "true");
        });

        // Đảm bảo nút gửi là hình tròn (Image 2 style)
        const sendBtn = document.getElementById("chat-submit");
        if (sendBtn) {
            sendBtn.style.borderRadius = "50%";
        }
    }

    // 4. Lấy thông tin user hiện tại và hiển thị nút Quản trị trên Header nếu là Admin
    async function checkCurrentUser() {
        if (currentUserChecked) return;
        try {
            const res = await fetch("/user");
            if (res.ok) {
                const user = await res.json();
                currentUserChecked = true;
                if (user && user.metadata && user.metadata.role === "admin") {
                    currentUserRole = "admin";
                    injectAdminHeaderButton();
                }
            }
        } catch (e) {
            // Chưa đăng nhập hoặc trang tĩnh
        }
    }

    function injectAdminHeaderButton() {
        if (currentUserRole !== "admin") return;
        if (document.getElementById("dhv-admin-header-btn")) return;

        // Tìm vị trí header actions: trước #theme-toggle hoặc trước #user-nav-button
        const themeToggle = document.getElementById("theme-toggle");
        const userNavBtn = document.getElementById("user-nav-button");
        const targetContainer = themeToggle ? themeToggle.parentElement : (userNavBtn ? userNavBtn.parentElement : null);

        if (!targetContainer) return;

        const adminBtn = document.createElement("button");
        adminBtn.id = "dhv-admin-header-btn";
        adminBtn.className = "dhv-admin-header-btn";
        adminBtn.innerHTML = `<span>🛡️</span> <span>Quản trị</span>`;
        adminBtn.title = "Mở Bảng điều khiển Quản trị viên";

        adminBtn.addEventListener("click", async function (e) {
            e.preventDefault();
            adminBtn.disabled = true;
            try {
                // Lấy bridge token phiên an toàn
                let bridgeToken = "";
                try {
                    const res = await fetch("/admin/bridge-token");
                    if (res.ok) {
                        const data = await res.json();
                        bridgeToken = data.token;
                    }
                } catch (err) {}

                if (!bridgeToken) {
                    try {
                        const res2 = await fetch("http://127.0.0.1:8000/admin/bridge-token");
                        if (res2.ok) {
                            const data2 = await res2.json();
                            bridgeToken = data2.token;
                        }
                    } catch (err2) {}
                }

                if (bridgeToken) {
                    window.open("/public/admin.html#token=" + bridgeToken, "_blank");
                } else {
                    window.open("/public/admin.html", "_blank");
                }
            } catch (err) {
                console.error("Lỗi mở Bảng điều khiển Admin:", err);
                window.open("/public/admin.html", "_blank");
            } finally {
                adminBtn.disabled = false;
            }
        });

        if (themeToggle) {
            targetContainer.insertBefore(adminBtn, themeToggle);
        } else if (userNavBtn) {
            targetContainer.insertBefore(adminBtn, userNavBtn);
        } else {
            targetContainer.appendChild(adminBtn);
        }
    }

    function runAllEnhancements() {
        enhanceLoginPage();
        enhanceComposer();
        if (!currentUserChecked) {
            checkCurrentUser();
        } else if (currentUserRole === "admin") {
            injectAdminHeaderButton();
        }
    }

    // Khởi chạy khi DOM sẵn sàng
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", runAllEnhancements);
    } else {
        runAllEnhancements();
    }

    // Theo dõi DOM mutations để duy trì giao diện khi React re-render
    let timeoutId = null;
    const observer = new MutationObserver(function () {
        if (timeoutId) clearTimeout(timeoutId);
        timeoutId = setTimeout(runAllEnhancements, 50);
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
