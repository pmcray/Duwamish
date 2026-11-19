; ======================================================================
;  GPS: THE GENERAL PROBLEM SOLVER -- after Newell, Shaw and Simon (1959)
;
;  GPS works by means-ends analysis.  To TRANSFORM a state into a goal it
;  finds the most important DIFFERENCE between them, and a table of
;  connections tells it which operator REDUCES that difference.  If the
;  operator cannot be APPLIED yet, making it applicable becomes a new
;  goal: transform the state into one where it can be.
;
;  Here it plays the Tower of Hanoi.  A state says which peg each disk
;  is on, smallest first; a goal says where some of the disks must be.
;  The differences are ordered by size: a misplaced large disk matters
;  more than a misplaced small one.  The one operator, MOVE, needs every
;  smaller disk out of the way, on the third peg.
;
;  Each disk is on one of three pegs, so a state of n disks is an n-trit
;  word, written here with A, B, C as T, 0, 1, largest disk first.
; ======================================================================

(define pegs '(A B C))
(define (other p q) (car (difference pegs (list p q))))

; the peg of disk d (1 is the smallest)
(define (peg d state) (nth d state))
(define (put d p state)
  (if (= d 1) (cons p (cdr state)) (cons (car state) (put (- d 1) p (cdr state)))))

(define zero (car (explode "0")))
(define one (car (explode "1")))
(define (trit p) (cond ((eq p 'A) 'T) ((eq p 'B) zero) (else one)))
(define (word state) (implode (reverse (mapcar trit state))))

; the most important difference: the largest disk not where the goal wants it
(define (difference-of state goal)
  (cond ((null goal) nil)
        ((eq (peg (car (car goal)) state) (cadr (car goal)))
         (difference-of state (cdr goal)))
        (else (car goal))))

(define goals 0)
(define moves 0)
(define tracing t)
(define (indent n) (if (> n 0) (progn (prin1 space) (prin1 space) (indent (- n 1))) nil))
(define (note depth words) (if tracing (progn (indent depth) (say words)) nil))

; goals list the largest disk first
(define (smaller-on d p)
  (if (= d 0) nil (cons (list d p) (smaller-on (- d 1) p))))

; TRANSFORM state INTO goal: returns the new state
(define (transform state goal depth)
  (setq goals (+ goals 1))
  (let ((d (difference-of state goal)))
    (cond ((null d) state)
          (else
           (note depth (list 'REDUCE 'THE 'DIFFERENCE: 'DISK (car d) 'IS 'NOT 'ON (cadr d)))
           (transform (reduce state d depth) goal depth)))))

; REDUCE: the table of connections has one entry -- a disk on the wrong
; peg is reduced by MOVE -- whose condition is that the smaller disks
; are all on the third peg
(define (reduce state d depth)
  (let ((disk (car d)) (to (cadr d)))
    (let ((via (other (peg disk state) to)))
      (let ((ready (if (= disk 1) state
                       (progn
                        (note depth (append (list 'TO 'MOVE 'DISK disk 'TO to 'FIRST 'PUT)
                                            (append (if (= disk 2) '(DISK 1)
                                                        (list 'DISKS 1 'TO (- disk 1)))
                                                    (list 'ON via))))
                        (transform state (smaller-on (- disk 1) via) (+ depth 1))))))
        (apply-move disk to ready depth)))))

(define (apply-move disk to state depth)
  (setq moves (+ moves 1))
  (let ((new (put disk to state)))
    (note depth (list 'MOVE disk 'FROM (peg disk state) 'TO to
                      'GIVING (word new)))
    new))

(define (all-on n p) (if (= n 0) nil (cons p (all-on (- n 1) p))))

(define (solve n trace)
  (setq goals 0)
  (setq moves 0)
  (setq tracing trace)
  (let ((start (all-on n 'A)))
    (say (list 'TRANSFORM (word start) 'INTO (word (all-on n 'C))))
    (transform start (smaller-on n 'C) 1)
    (say (list n 'DISKS: moves 'MOVES 'FROM goals 'GOALS))
    (terpri)))

(say '(GPS AND THE TOWER OF HANOI))
(terpri)
(solve 3 t)
(solve 4 nil)
(solve 5 nil)
(solve 6 nil)
(say '(THE MOVES ARE 2 TO THE N MINUS 1 -- THE FEWEST POSSIBLE -- AND GPS))
(say '(NEVER SEARCHES: THE ORDER OF THE DIFFERENCES DOES ALL THE WORK))
