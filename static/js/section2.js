function handleSearch() {
    const searchTerm = document.getElementById('unifiedSearch').value.trim();
    if (!searchTerm) return;

    fetch('/community-search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `searchTerm=${searchTerm}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
            return;
        }

        const iframe = document.querySelector('iframe');
        const iframeWindow = iframe.contentWindow;
        const network = iframeWindow.network;

        if (!network) {
            alert('Network not loaded yet. Please try again.');
            return;
        }

        network.unselectAll();

        if (data.type === 'community') {
            // Highlight all nodes in the community
            network.selectNodes(data.nodes.map(String));
            network.fit({
                nodes: data.nodes.map(String),
                animation: {
                    duration: 1000,
                    easingFunction: 'easeInOutQuad'
                }
            });
            alert(`Highlighted Community ${data.id} with ${data.count} nodes`);
            
            // Find and expand the size group and community
            const communityId = data.id;
            const sizeGroups = document.querySelectorAll('.size-group-header');
            sizeGroups.forEach(group => {
                const size = group.id.split('-')[2];
                const content = document.getElementById(`size-group-${size}`);
                const commContent = document.getElementById(`community-${communityId}`);
                
                if (commContent) {
                    content.classList.add('show');
                    group.querySelector('.toggle-icon').classList.add('rotated');
                    commContent.classList.add('show');
                    
                    // Highlight the community badge
                    const badges = document.querySelectorAll('.community-badge');
                    badges.forEach(badge => {
                        if (badge.textContent.includes(`Community ${communityId}`)) {
                            badge.classList.add('active');
                        }
                    });
                }
            });
            
        } else if (data.type === 'node') {
            // Highlight the single node
            const nodeIdStr = String(data.id);
            network.selectNodes([nodeIdStr]);
            network.focus(nodeIdStr, {
                scale: 1.5,
                animation: {
                    duration: 1000,
                    easingFunction: 'easeInOutQuad'
                }
            });
            
            // Show node info
            fetch(`/node-info/${data.id}`)
                .then(response => response.json())
                .then(nodeData => {
                    alert(
                        `Node ${nodeData.id} Information:\n` +
                        `Community: ${nodeData.community}\n` +
                        `Category: ${nodeData.category}\n` +
                        `Degree Centrality: ${nodeData.degree.toFixed(2)}\n` +
                        `Betweenness Centrality: ${nodeData.betweenness.toFixed(4)}`
                    );
                });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error performing search');
    });
}

function toggleSizeGroup(size) {
    const content = document.getElementById(`size-group-${size}`);
    const icon = content.previousElementSibling.querySelector('.toggle-icon');
    content.classList.toggle('show');
    icon.classList.toggle('rotated');
}

function toggleCommunity(comm, event) {
    // Stop event bubbling so we don't trigger the size group toggle
    event.stopPropagation();
    
    const content = document.getElementById(`community-${comm}`);
    content.classList.toggle('show');
    
    // Highlight the community badge
    const badges = document.querySelectorAll('.community-badge');
    badges.forEach(badge => {
        if (badge.textContent.includes(`Community ${comm}`)) {
            badge.classList.toggle('active');
        }
    });
}

function sortTable(columnIndex, isNumeric = false) {
    const table = document.querySelector('.transaction-table table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tbody.community-content tr'));
    let sortOrder = 1;

    rows.sort((a, b) => {
        let aVal = a.cells[columnIndex].textContent;
        let bVal = b.cells[columnIndex].textContent;

        if (isNumeric) {
            aVal = parseFloat(aVal.replace(/,/g, ''));
            bVal = parseFloat(bVal.replace(/,/g, ''));
            return (bVal - aVal) * sortOrder;
        }
        return aVal.localeCompare(bVal) * sortOrder;
    });

    sortOrder = -sortOrder;

    // Rebuild the table while maintaining community structure
    const communities = {};
    rows.forEach(row => {
        const communityId = row.closest('tbody.community-content').id.split('-')[1];
        if (!communities[communityId]) {
            communities[communityId] = [];
        }
        communities[communityId].push(row);
    });

    // Clear and rebuild the table
    tbody.innerHTML = '';
    
    // Get all size groups
    const sizeGroups = Array.from(document.querySelectorAll('.size-group-header')).map(group => {
        const size = group.id.split('-')[2];
        return {
            header: group.cloneNode(true),
            size: size,
            communities: []
        };
    });

    // Rebuild the table structure
    sizeGroups.forEach(sizeGroup => {
        tbody.appendChild(sizeGroup.header);
        const sizeContent = document.createElement('tbody');
        sizeContent.id = `size-group-${sizeGroup.size}`;
        sizeContent.className = 'size-group-content';
        
        // Add community list
        const communityListRow = document.createElement('tr');
        communityListRow.innerHTML = `<td colspan="6"><div class="community-list"></div></td>`;
        sizeContent.appendChild(communityListRow);
        
        // Add communities and their transactions
        for (const [commId, commRows] of Object.entries(communities)) {
            const commContent = document.createElement('tbody');
            commContent.id = `community-${commId}`;
            commContent.className = 'community-content';
            commRows.forEach(row => commContent.appendChild(row));
            sizeContent.appendChild(commContent);
        }
        
        tbody.appendChild(sizeContent);
    });
}