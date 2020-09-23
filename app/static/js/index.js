let body = document.body,
    checkboxes = document.querySelectorAll('input[type="checkbox"]'),
    allCheckboxes = document.querySelectorAll('input[type="checkbox"][name$="-all"]'),
    query = document.getElementById('query'),
    submit = document.getElementById('submit'),
    sections = document.getElementsByTagName('section'),
    output = document.getElementById('output');

function resetFilters() {
    for (let checkbox of checkboxes) {
        checkbox.checked = false;
    }
    for (let checkbox of allCheckboxes) {
        checkbox.checked = true;
    }
}
resetFilters();

onchange = function(e) {
    let input = e.target;
    if (input.type === 'checkbox') {
        let checked = input.checked;
        let otherCheckboxes = Array.from(input.parentElement.parentElement.getElementsByTagName('input'));
        let allCheckbox = otherCheckboxes.shift();
        if (input == allCheckbox) {
            for (let checkbox of otherCheckboxes) {
                checkbox.checked = !checked;
            }
        } else {
            if (checked) {
                allCheckbox.checked = false;
            } else {
                let anyChecked = false;
                for (let checkbox of otherCheckboxes) {
                    anyChecked = anyChecked || checkbox.checked;
                }
                allCheckbox.checked = !anyChecked;
            }
        }
    }
};

query.onkeyup = function(e) {
    if (e.keyCode === 13) {
        e.preventDefault();
        submit.click();
    }
};

let criteria = {};
let pagesLoaded = 0;
let pagesFinished = false;

function loadNextPage() {
    if (!pagesFinished) {
        criteria['page'] = ++pagesLoaded;
        fetch('/api/students', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(criteria),
        })
            .then(response => response.json())
            .then(students => {
                console.log(students);
                pagesFinished = (students.length < 20);
                for (let student of students) {
                    let studentContainer = document.createElement('div');
                    studentContainer.className = 'student';

                    let img = document.createElement('img');
                    img.className = 'image';
                    if (student.image) {
                        img.src = student.image;
                    } else {
                        img.src = '/static/images/user.png';
                    }
                    studentContainer.appendChild(img);
                    let name = document.createElement('h3');
                    name.className = 'name';
                    name.textContent = student.last_name + ', ' + student.first_name;
                    studentContainer.appendChild(name);

                    if (student.netid || student.upi) {
                        let pills = document.createElement('div');
                        pills.className = 'pills';
                        if (student.netid) {
                            let pill = document.createElement('div');
                            pill.className = 'pill';
                            pill.textContent = 'NetID ' + student.netid;
                            pills.appendChild(pill);
                        }
                        if (student.upi) {
                            let pill = document.createElement('div');
                            pill.className = 'pill';
                            pill.textContent = 'UPI ' + student.upi;
                            pills.appendChild(pill);
                        }
                        studentContainer.appendChild(pills);
                    }
                    addRow(studentContainer, 'year', 'calendar', student);
                    if (student.leave) {
                        let row = document.createElement('div');
                        row.classList.add('row');
                        row.classList.add('leave');
                        let i = document.createElement('i');
                        i.className = 'fa fa-' + 'hourglass';
                        row.appendChild(i);
                        let readout = document.createElement('p');
                        readout.classList.add('value');
                        readout.classList.add('leave');
                        readout.textContent = 'On Leave';
                        row.appendChild(readout);

                        studentContainer.appendChild(row);
                    }
                    addRow(studentContainer, 'college', 'graduation-cap', student);
                    addRow(studentContainer, 'email', 'envelope', student, 'mailto');
                    addRow(studentContainer, 'residence', 'building', student);
                    addRow(studentContainer, 'major', 'book', student);
                    addRow(studentContainer, 'phone', 'phone', student, 'tel');
                    addRow(studentContainer, 'birthday', 'birthday-cake', student);
                    addRow(studentContainer, 'access_code', 'key', student);
                    addRow(studentContainer, 'address', 'home', student);

                    output.appendChild(studentContainer);
                }
            });
    }
}

loadNextPage();

function addRow(container, property, icon, student, protocol) {
    let value = student[property];
    if (value) {
        let row = document.createElement('div');
        row.classList.add('row');
        row.classList.add(property);
        let i = document.createElement('i');
        i.className = 'fa fa-' + icon;
        row.appendChild(i);
        let readout = document.createElement('p');
        readout.classList.add('value');
        readout.classList.add(property);
        if (typeof(value) == 'string' && value.includes('\n')) {
            let lines = value.split('\n');
            readout.appendChild(document.createTextNode(lines.shift()));
            for (let line of lines) {
                readout.appendChild(document.createElement('br'));
                readout.appendChild(document.createTextNode(line));
            }
        } else if (protocol) {
            let a = document.createElement('a');
            a.href = protocol + ':' + value;
            a.textContent = value;
            readout.appendChild(a);
        } else {
            readout.textContent = value;
        }
        row.appendChild(readout);

        container.appendChild(row);
    }
}

submit.onclick = function() {
    let filters = {};
    for (let section of sections) {
        let category = section.id;
        let otherCheckboxes = Array.from(section.getElementsByTagName('input'));
        let allCheckbox = otherCheckboxes.shift();
        if (!allCheckbox.checked) {
            filters[category] = []
            for (let checkbox of otherCheckboxes) {
                if (checkbox.checked) {
                    if (category === 'leave') {
                        filters[category].push(checkbox.name === 'Yes');
                    } else {
                        filters[category].push(checkbox.name);
                    }
                }
            }
        }
    }
    criteria = {
        'query': query.value,
        'filters': filters,
    };
    output.innerHTML = '';
    pagesLoaded = 0;
    pagesFinished = false;
    loadNextPage();
};

onclick = function(e) {
    let section = null;
    if (e.target.tagName == 'SECTION') section = e.target;
    if (e.target.tagName == 'H4' && e.target.parentElement.tagName == 'SECTION') section = e.target.parentElement;

    if (section) {
        section.classList.toggle('collapsed');
    }
};

window.onscroll = function(e) {
    if (2 * window.innerHeight + window.scrollY >= document.body.offsetHeight) {
        loadNextPage();
    }
}
