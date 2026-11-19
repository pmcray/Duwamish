; ======================================================================
;  A THREE-VALUED PROLOG
;
;  Logic programming began in 1972 (Colmerauer and Roussel's Prolog, from
;  Kowalski's procedural reading of Horn clauses and Robinson's
;  resolution).  Prolog has two answers, yes and no, and "no" means only
;  "not proved": negation as failure, the closed-world assumption.  On
;  a ternary machine a question can have three answers:
;
;    TRUE      proved
;    FALSE     its negation proved -- by a clause whose head is (NOT ...),
;              or because the predicate is declared CLOSED and nothing
;              proves it
;    UNKNOWN   neither; or the search went deeper than its bound
;
;  (NOT p) in a body is Kleene's negation of p's three-valued truth, and
;  a body is the Kleene conjunction, the minimum, of its literals.
;  Each answer is printed beside the one Prolog's negation as failure
;  would give, to show where the two differ.
; ======================================================================

(define qmark (car (explode "?")))
(define (var x) (and (consp x) (eq (car x) 'VAR)))

; ?X becomes a cell (VAR ?X); a fresh cell is made for each use of a
; clause, so the variables of different uses are different
(define (prep x vars)
  (cond ((consp x)
         (let ((a (prep (car x) vars)))
           (let ((d (prep (cdr x) (cdr a))))
             (cons (cons (car a) (car d)) (cdr d)))))
        ((and (symbolp x) x (eq (car (explode x)) qmark))
         (let ((p (assoc x vars)))
           (if p (cons (cadr p) vars)
               (let ((c (list 'VAR x)))
                 (cons c (cons (list x c) vars))))))
        (else (cons x vars))))
(define (prepare clause) (car (prep clause nil)))

; renaming a clause: a map from its cells to fresh ones
(define (rename x m)
  (cond ((var x)
         (let ((p (assq x (car m))))
           (if p (cadr p)
               (let ((c (list 'VAR (cadr x))))
                 (rplaca m (cons (list x c) (car m)))
                 c))))
        ((consp x) (cons (rename (car x) m) (rename (cdr x) m)))
        (else x)))
(define (fresh clause) (rename clause (list nil)))

(define (assq k l)
  (cond ((null l) nil) ((eq k (car (car l))) (car l)) (else (assq k (cdr l)))))
(define (walk x b)
  (let ((p (and (var x) (assq x b))))
    (if p (walk (cadr p) b) x)))
(define (subst x b)
  (cond ((var x) (let ((v (walk x b))) (if (var v) v (subst v b))))
        ((consp x) (cons (subst (car x) b) (subst (cdr x) b)))
        (else x)))
(define (ground x b)
  (cond ((var x) (not (var (walk x b))))
        ((consp x) (and (ground (car x) b) (ground (cdr x) b)))
        (else t)))

(define (unify x y b)
  (cond ((eq b 'FAIL) 'FAIL)
        (else
         (let ((x (walk x b)) (y (walk y b)))
           (cond ((eq x y) b)
                 ((var x) (cons (list x y) b))
                 ((var y) (cons (list y x) b))
                 ((and (consp x) (consp y))
                  (unify (cdr x) (cdr y) (unify (car x) (car y) b)))
                 ((equal x y) b)
                 (else 'FAIL))))))

; ----------------------------------------------------------------------
;  the database
; ----------------------------------------------------------------------
(define clauses nil)
(define closed nil)
(define (fact . cls) (setq clauses (append clauses (mapcar prepare cls))))
(define (close-pred p) (setq closed (cons p closed)))

(define (positive c) (not (eq (car (car c)) 'NOT)))

; ----------------------------------------------------------------------
;  the prover.  solve returns a list of (bindings value), value 1 for
;  true or 0 for unknown; false answers are simply absent.  In NAF mode it
;  is ordinary Prolog: no unknowns, and NOT is failure to prove.
; ----------------------------------------------------------------------
(define naf nil)
(define cutoff nil)

(define (solve goals b depth)
  (cond ((null goals) (list (list b 1)))
        (else
         (let ((firsts (literal (car goals) b depth)))
           (conj firsts (cdr goals) depth)))))

(define (conj firsts rest depth)
  (cond ((null firsts) nil)
        (else
         (append (mapcar (lambda (s) (list (car s) (min (cadr (car firsts)) (cadr s))))
                         (solve rest (car (car firsts)) depth))
                 (conj (cdr firsts) rest depth)))))

(define (min a b) (if (< a b) a b))

(define (literal g b depth)
  (cond ((eq (car g) 'NOT)
         (let ((v (truth (cadr g) b depth)))
           (cond ((= v -1) (list (list b 1)))
                 ((= v 0) (list (list b 0)))
                 (else nil))))
        ((= depth 0) (setq cutoff t) (list (list b 0)))
        (else
         (let ((sols (by-clauses g b depth clauses)))
           (cond (sols sols)
                 (naf nil)
                 ((member (car g) closed) nil)
                 ((and (ground g b) (= (truth-of-not g b depth) 1)) nil)
                 ((ground g b) (list (list b 0)))
                 (else nil))))))

(define (by-clauses g b depth cls)
  (cond ((null cls) nil)
        ((and (positive (car cls)) (eq (car (car (car cls))) (car g)))
         (let ((c (fresh (car cls))))
           (let ((b2 (unify (car c) g b)))
             (append (if (eq b2 'FAIL) nil (solve (cdr c) b2 (- depth 1)))
                     (by-clauses g b depth (cdr cls))))))
        (else (by-clauses g b depth (cdr cls)))))

; is (NOT g) proved by a clause whose head is (NOT ...)?  1 or 0
(define (truth-of-not g b depth)
  (if naf 0 (best (not-clauses g b depth clauses))))

(define (not-clauses g b depth cls)
  (cond ((null cls) nil)
        ((not (positive (car cls)))
         (let ((c (fresh (car cls))))
           (let ((b2 (unify (cadr (car c)) g b)))
             (append (if (eq b2 'FAIL) nil (solve (cdr c) b2 (- depth 1)))
                     (not-clauses g b depth (cdr cls))))))
        (else (not-clauses g b depth (cdr cls)))))

(define (best sols)
  (cond ((null sols) -1)
        ((= (cadr (car sols)) 1) 1)
        (else (let ((r (best (cdr sols)))) (if (= r 1) 1 0)))))

; the three-valued truth of a ground literal
(define (truth g b depth)
  (let ((s (best (literal g b depth))))
    (cond ((= s 1) 1)
          (naf -1)
          ((= (truth-of-not g b depth) 1) -1)
          ((= s 0) 0)
          ((member (car g) closed) -1)
          (else 0))))

; ----------------------------------------------------------------------
;  asking
; ----------------------------------------------------------------------
(define depth 8)
(define (word v) (cond ((= v 1) 'TRUE) ((= v -1) 'FALSE) (else 'UNKNOWN)))

(define (pad words n)
  (say-inline words)
  (spaces (- n (width words))))
; how wide a list of things is in print
(define (width words)
  (if (null words) 0
      (+ (w (car words)) (if (cdr words) 1 0) (width (cdr words)))))
(define (w x)
  (cond ((null x) 3)
        ((numberp x) (if (< x 0) (+ 1 (ndig (- 0 x))) (ndig x)))
        ((symbolp x) (length (explode x)))
        (else (+ 2 (width x)))))
(define (ndig n) (if (< n 10) 1 (+ 1 (ndig (/ n 10)))))
(define (say-inline words)
  (cond ((null words) nil)
        (else (prin1 (car words))
              (if (cdr words) (prin1 space) nil)
              (say-inline (cdr words)))))
(define (spaces n) (if (> n 0) (progn (prin1 space) (spaces (- n 1))) nil))

(define (ask q)
  (let ((g (prepare q)))
    (setq cutoff nil)
    (setq naf nil)
    (let ((v3 (if (ground g nil) (word (truth g nil depth)) (answers g))))
      (setq cutoff nil)
      (setq naf t)
      (let ((v2 (if (ground g nil)
                    (if (= (best (literal g nil depth)) 1) 'YES 'NO)
                    (answers g))))
        (setq naf nil)
        (prin1 space) (prin1 space)
        (pad (list q) 30)
        (pad (if (consp v3) v3 (list v3)) 22)
        ; a NO that came from the depth bound: Prolog would never answer
        (if (and cutoff (eq v2 'NO)) (say '(NO ANSWER -- IT LOOPS))
            (say (if (consp v2) v2 (list v2))))))))

; the answers to a question with variables: each binding of its first
; variable, true ones plain and unknown ones marked ?
(define (answers g)
  (let ((v (first-var g)))
    (let ((sols (solve (list g) nil depth)))
      (if (null sols) '(NONE)
          (dedupe (mapcar (lambda (s)
                            (let ((x (subst v (car s))))
                              (if (= (cadr s) 1) x (implode (append (explode x) (list qmark))))))
                          sols))))))
(define (first-var x)
  (cond ((var x) x) ((consp x) (or (first-var (car x)) (first-var (cdr x)))) (else nil)))
(define (dedupe l)
  (cond ((null l) nil) ((member (car l) (cdr l)) (dedupe (cdr l)))
        (else (cons (car l) (dedupe (cdr l))))))

(define (header)
  (prin1 space) (prin1 space)
  (pad '(QUESTION) 30) (pad '(THREE VALUES) 22) (say '(PROLOG)))

(say '(A THREE-VALUED PROLOG))
(terpri)

; 1. a family: here PARENT is all there is to know, so it is CLOSED
(fact '((PARENT TOM BOB)) '((PARENT TOM LIZ)) '((PARENT BOB ANN))
      '((PARENT BOB PAT)) '((PARENT PAT JIM))
      '((GRANDPARENT ?X ?Z) (PARENT ?X ?Y) (PARENT ?Y ?Z))
      '((ANCESTOR ?X ?Y) (PARENT ?X ?Y))
      '((ANCESTOR ?X ?Y) (PARENT ?X ?Z) (ANCESTOR ?Z ?Y)))
(close-pred 'PARENT)
(close-pred 'GRANDPARENT)
(close-pred 'ANCESTOR)
(say '(1. A FAMILY -- PARENT IS CLOSED: WHAT IS NOT RECORDED IS FALSE))
(header)
(ask '(GRANDPARENT TOM ANN))
(ask '(PARENT ANN TOM))
(ask '(ANCESTOR TOM ?WHO))
(ask '(GRANDPARENT ?WHO JIM))
(terpri)

; 2. birds: an open world, where what is not recorded is not known
(fact '((BIRD TWEETY)) '((BIRD POLLY)) '((BIRD OPUS)) '((PENGUIN OPUS))
      '((NOT (PENGUIN POLLY)))
      '((FLIES ?X) (BIRD ?X) (NOT (PENGUIN ?X)))
      '((NOT (FLIES ?X)) (PENGUIN ?X)))
(say '(2. BIRDS -- AN OPEN WORLD: WE ARE TOLD POLLY IS NO PENGUIN))
(say '(AND OPUS IS ONE -- BUT NOTHING ABOUT TWEETY))
(header)
(ask '(FLIES POLLY))
(ask '(FLIES OPUS))
(ask '(FLIES TWEETY))
(ask '(FLIES ?WHO))
(ask '(PENGUIN TWEETY))
(terpri)

; 3. a question that goes round in circles
(fact '((LIKES ANN BOB)) '((LIKES ?X ?Y) (LIKES ?Y ?X)))
(say '(3. LIKING IS MUTUAL: (LIKES ?X ?Y) IF (LIKES ?Y ?X)))
(header)
(ask '(LIKES BOB ANN))
(ask '(LIKES BOB CAROL))
(terpri)
(say '(A ? MARKS AN ANSWER THAT MAY BE SO BUT IS NOT PROVED.  WHERE PROLOG))
(say '(SAYS TWEETY FLIES IT HAS ASSUMED THAT WHAT IT CANNOT PROVE IS FALSE))
(say '(-- THAT TWEETY IS NO PENGUIN.  AND WHERE THE SEARCH GOES ROUND IN))
(say '(CIRCLES THE BOUNDED PROVER SAYS UNKNOWN: IT CANNOT TELL NOT YET FROM))
(say '(NEVER -- WHICH IS THE LESSON OF HOFSTADTERS FLOOP AGAIN.))
