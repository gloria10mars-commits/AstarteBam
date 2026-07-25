document.addEventListener('DOMContentLoaded', () => {
    const board = document.getElementById('board');
    
    // Creation d'une grille 15x15 pour representer le plateau de Ludo
    for(let i = 0; i < 225; i++) {
        const cell = document.createElement('div');
        cell.classList.add('cell');
        
        let row = Math.floor(i / 15);
        let col = i % 15;
        
        // Coloration des coins (bases des joueurs) et du centre (home)
        if (row < 6 && col < 6) cell.classList.add('red');
        else if (row < 6 && col > 8) cell.classList.add('green');
        else if (row > 8 && col < 6) cell.classList.add('blue');
        else if (row > 8 && col > 8) cell.classList.add('yellow');
        else if (row > 5 && row < 9 && col > 5 && col < 9) cell.classList.add('home');
        else cell.classList.add('path');
        
        board.appendChild(cell);
    }

    const rollBtn = document.getElementById('roll-dice');
    const resultText = document.getElementById('dice-result');
    const currentPlayerSpan = document.getElementById('current-player');
    
    // Ordre des joueurs : Rouge -> Vert -> Jaune -> Bleu
    const players = [
        { name: 'Rouge', class: 'text-red' },
        { name: 'Vert', class: 'text-green' },
        { name: 'Jaune', class: 'text-yellow' },
        { name: 'Bleu', class: 'text-blue' }
    ];
    let playerIndex = 0;

    rollBtn.addEventListener('click', () => {
        // Animation rapide pour le de
        let count = 0;
        rollBtn.disabled = true;
        let interval = setInterval(() => {
            const tempDice = Math.floor(Math.random() * 6) + 1;
            resultText.innerText = `Résultat: ${tempDice}`;
            count++;
            
            if(count > 10) {
                clearInterval(interval);
                // Resultat final
                const finalDice = Math.floor(Math.random() * 6) + 1;
                resultText.innerText = `Résultat: ${finalDice}`;
                
                // Si le joueur ne fait pas 6, c'est au tour du suivant
                if (finalDice !== 6) {
                    playerIndex = (playerIndex + 1) % players.length;
                    currentPlayerSpan.innerText = players[playerIndex].name;
                    currentPlayerSpan.className = players[playerIndex].class;
                }
                rollBtn.disabled = false;
            }
        }, 50);
    });
});
