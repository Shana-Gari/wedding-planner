// Admin-specific JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Image preview functionality
    document.querySelectorAll('.image-upload').forEach(input => {
        input.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                const previewId = this.dataset.preview;
                const preview = document.getElementById(previewId);
                
                reader.onload = function(event) {
                    preview.src = event.target.result;
                    preview.classList.remove('d-none');
                }
                reader.readAsDataURL(file);
            }
        });
    });
});