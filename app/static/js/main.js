// Main JavaScript file for Online Examination System

// Global variables
let currentUser = null;
let examSession = null;

// Initialize when document is ready
$(document).ready(function() {
    initializeApp();
});

function initializeApp() {
    // Enable all tooltips
    $('[data-toggle="tooltip"]').tooltip();
    
    // Enable all popovers
    $('[data-toggle="popover"]').popover();
    
    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        $('.alert').fadeOut('slow');
    }, 5000);
    
    // Add active class to current nav item
    highlightCurrentNav();
    
    // Initialize any date pickers
    initializeDatePickers();
    
    // Initialize file upload previews
    initializeFileUploads();
}

// Highlight current navigation item
function highlightCurrentNav() {
    let currentPath = window.location.pathname;
    $('.nav-link').each(function() {
        if ($(this).attr('href') === currentPath) {
            $(this).addClass('active');
        }
    });
}

// Initialize date pickers
function initializeDatePickers() {
    $('input[type="date"]').each(function() {
        $(this).attr('min', new Date().toISOString().split('T')[0]);
    });
}

// Initialize file uploads with preview
function initializeFileUploads() {
    $('input[type="file"]').change(function(e) {
        let fileName = e.target.files[0]?.name;
        if (fileName) {
            $(this).next('.custom-file-label').text(fileName);
        }
    });
}

// AJAX helper function
function ajaxRequest(url, method = 'GET', data = null, successCallback = null, errorCallback = null) {
    $.ajax({
        url: url,
        method: method,
        data: data,
        contentType: method === 'POST' ? 'application/json' : undefined,
        success: function(response) {
            if (successCallback) {
                successCallback(response);
            }
        },
        error: function(xhr, status, error) {
            console.error('AJAX Error:', error);
            if (errorCallback) {
                errorCallback(xhr, status, error);
            } else {
                showNotification('An error occurred. Please try again.', 'error');
            }
        }
    });
}

// Show notification toast
function showNotification(message, type = 'info') {
    let alertClass = 'alert-info';
    let icon = 'fa-info-circle';
    
    switch(type) {
        case 'success':
            alertClass = 'alert-success';
            icon = 'fa-check-circle';
            break;
        case 'error':
            alertClass = 'alert-danger';
            icon = 'fa-exclamation-circle';
            break;
        case 'warning':
            alertClass = 'alert-warning';
            icon = 'fa-exclamation-triangle';
            break;
    }
    
    let notificationHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show position-fixed" 
             style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
            <i class="fas ${icon}"></i> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    $('body').append(notificationHtml);
    
    // Auto remove after 5 seconds
    setTimeout(function() {
        $('.position-fixed.alert').fadeOut('slow', function() {
            $(this).remove();
        });
    }, 5000);
}

// Confirm dialog
function confirmAction(message, callback) {
    if (confirm(message)) {
        if (callback) {
            callback();
        }
        return true;
    }
    return false;
}

// Format date
function formatDate(dateString) {
    let date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Format time
function formatTime(dateString) {
    let date = new Date(dateString);
    return date.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Table search functionality
function initializeTableSearch(tableId, searchInputId) {
    $(`#${searchInputId}`).on('keyup', function() {
        let value = $(this).val().toLowerCase();
        $(`#${tableId} tbody tr`).filter(function() {
            $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1);
        });
    });
}

// Dynamic form validation
function validateForm(formId) {
    let form = $(`#${formId}`);
    let isValid = true;
    
    form.find('input[required], select[required], textarea[required]').each(function() {
        if (!$(this).val()) {
            $(this).addClass('is-invalid');
            isValid = false;
        } else {
            $(this).removeClass('is-invalid');
        }
    });
    
    return isValid;
}

// Loading spinner
function showLoading(elementId) {
    $(`#${elementId}`).html(`
        <div class="text-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Loading...</p>
        </div>
    `);
}

// Print functionality
function printElement(elementId) {
    let printContents = document.getElementById(elementId).innerHTML;
    let originalContents = document.body.innerHTML;
    
    document.body.innerHTML = printContents;
    window.print();
    document.body.innerHTML = originalContents;
    location.reload();
}

// Export to CSV
function exportToCSV(tableId, filename) {
    let csv = [];
    let rows = document.querySelectorAll(`#${tableId} tr`);
    
    for (let i = 0; i < rows.length; i++) {
        let row = [], cols = rows[i].querySelectorAll('td, th');
        
        for (let j = 0; j < cols.length; j++) {
            row.push(cols[j].innerText);
        }
        
        csv.push(row.join(','));
    }
    
    // Download CSV
    let csvFile = new Blob([csv.join('\n')], {type: 'text/csv'});
    let downloadLink = document.createElement('a');
    downloadLink.download = filename || 'export.csv';
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
}

// Timer functionality
function startTimer(duration, displayElement, callback) {
    let timer = duration;
    let minutes, seconds;
    
    let interval = setInterval(function() {
        minutes = parseInt(timer / 60, 10);
        seconds = parseInt(timer % 60, 10);
        
        minutes = minutes < 10 ? "0" + minutes : minutes;
        seconds = seconds < 10 ? "0" + seconds : seconds;
        
        $(displayElement).text(minutes + ":" + seconds);
        
        if (--timer < 0) {
            clearInterval(interval);
            if (callback) {
                callback();
            }
        }
    }, 1000);
    
    return interval;
}

// Prevent multiple form submissions
function preventDoubleSubmission(formId) {
    $(`#${formId}`).on('submit', function() {
        $(this).find('button[type="submit"]').prop('disabled', true);
        setTimeout(function() {
            $(this).find('button[type="submit"]').prop('disabled', false);
        }, 3000);
    });
}

// Image preview for file uploads
function previewImage(input, previewElement) {
    if (input.files && input.files[0]) {
        let reader = new FileReader();
        
        reader.onload = function(e) {
            $(`#${previewElement}`).attr('src', e.target.result);
            $(`#${previewElement}`).show();
        };
        
        reader.readAsDataURL(input.files[0]);
    }
}

// Dynamic select population
function populateSelect(selectId, data, valueKey, textKey, placeholder = 'Select...') {
    let select = $(`#${selectId}`);
    select.empty();
    select.append(`<option value="">${placeholder}</option>`);
    
    data.forEach(function(item) {
        select.append(`<option value="${item[valueKey]}">${item[textKey]}</option>`);
    });
}

// Debounce function for search inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Exam lockdown features
function enableExamLockdown() {
    // Prevent right-click
    document.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        return false;
    });
    
    // Prevent keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Prevent Ctrl+C, Ctrl+V, Ctrl+U, Ctrl+S, Ctrl+P
        if (e.ctrlKey && (e.key === 'c' || e.key === 'v' || e.key === 'u' || e.key === 's' || e.key === 'p')) {
            e.preventDefault();
            return false;
        }
        
        // Prevent F12 (Developer Tools)
        if (e.key === 'F12') {
            e.preventDefault();
            return false;
        }
        
        // Prevent Ctrl+Shift+I (Developer Tools)
        if (e.ctrlKey && e.shiftKey && e.key === 'I') {
            e.preventDefault();
            return false;
        }
    });
    
    // Warn on tab/window close
    window.addEventListener('beforeunload', function(e) {
        e.preventDefault();
        e.returnValue = 'Are you sure you want to leave? Your exam progress may be lost.';
        return e.returnValue;
    });
}

// Disable exam lockdown
function disableExamLockdown() {
    // Remove all event listeners added by lockdown
    // Note: This is a simplified version, actual implementation may vary
    window.removeEventListener('beforeunload', function() {});
}

// Auto-save functionality for exams
function autoSave(saveFunction, interval = 30000) {
    setInterval(function() {
        saveFunction();
        showNotification('Progress auto-saved', 'info');
    }, interval);
}

// Countdown timer for exams
class ExamTimer {
    constructor(duration, displayElement, onComplete) {
        this.duration = duration;
        this.display = displayElement;
        this.onComplete = onComplete;
        this.remaining = duration;
        this.interval = null;
    }
    
    start() {
        this.interval = setInterval(() => {
            this.remaining--;
            this.updateDisplay();
            
            if (this.remaining <= 300) { // 5 minutes warning
                $(this.display).addClass('text-danger');
            }
            
            if (this.remaining <= 0) {
                this.stop();
                if (this.onComplete) {
                    this.onComplete();
                }
            }
        }, 1000);
    }
    
    stop() {
        clearInterval(this.interval);
    }
    
    updateDisplay() {
        let minutes = Math.floor(this.remaining / 60);
        let seconds = this.remaining % 60;
        $(this.display).text(
            `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
        );
    }
    
    getElapsed() {
        return this.duration - this.remaining;
    }
    
    getRemaining() {
        return this.remaining;
    }
}

// Initialize on page load
$(function() {
    // Add CSRF token to all AJAX requests if needed
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                // xhr.setRequestHeader("X-CSRFToken", csrf_token);
            }
        }
    });
    
    // Make functions globally available
    window.showNotification = showNotification;
    window.confirmAction = confirmAction;
    window.ajaxRequest = ajaxRequest;
});