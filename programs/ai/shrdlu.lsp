; ======================================================================
;  MICRO-SHRDLU -- after Terry Winograd (MIT, 1970-72)
;
;  A robot arm, a table, a box, and some blocks and pyramids.  The
;  program parses what it is told, finds what the words refer to --
;  using what was said before to settle "the pyramid", "it" and "them"
;  -- and then answers, or plans and carries out the moves.  It asks
;  when a description fits more than one thing, and says when it does
;  not know.
;
;  The world is built so that the first part of the dialogue printed in
;  Winograd's "Understanding Natural Language" (1972) can be followed;
;  what the robot does to carry out a command is shown in brackets.
;  The grammar is a handful of sentence patterns, where Winograd's was a
;  large procedural grammar; the question-answering keeps his rule of
;  three answers: yes if the world shows an example, no if it knows a
;  reason, and otherwise "I don't know".
; ======================================================================

; (name shape colour size width height)
(define objects
  '((B1 BLOCK RED LARGE 2 3)
    (B2 BLOCK GREEN SMALL 2 1)
    (P3 PYRAMID BLUE SMALL 1 1)
    (B4 BLOCK BLUE LARGE 2 4)
    (B5 BLOCK RED SMALL 1 1)
    (B6 BLOCK GREEN LARGE 2 2)
    (P1 PYRAMID GREEN SMALL 1 1)
    (P2 PYRAMID RED SMALL 1 1)
    (BOX BOX WHITE LARGE 3 2)
    (TABLE TABLE BROWN LARGE 9 1)))

; what each object stands on, or is in
(define support
  '((B1 TABLE) (B2 B1) (P3 BOX) (B4 TABLE) (B5 TABLE) (B6 TABLE) (P1 B6)
    (P2 TABLE) (BOX TABLE)))

(define holding nil)
(define told nil)            ; what the robot was told to pick up
(define focus nil)           ; the things just talked about
(define it nil)
(define them nil)
(define learned nil)         ; what the robot has found it cannot do

(define (info x) (assoc x objects))
(define (shape x) (nth 2 (info x)))
(define (colour x) (nth 3 (info x)))
(define (size x) (nth 4 (info x)))
(define (width x) (nth 5 (info x)))
(define (height x) (nth 6 (info x)))
(define (cube x) (and (eq (shape x) 'BLOCK) (= (width x) (height x))))
(define (on x) (cadr (assoc x support)))

; ----------------------------------------------------------------------
;  words
; ----------------------------------------------------------------------
(define marks (list (car (explode ",")) (car (explode ".")) (car (explode "?"))))
(define (tokens chars word acc)
  (cond ((null chars) (reverse (if word (cons (implode (reverse word)) acc) acc)))
        ((or (eq (car chars) space) (member (car chars) marks))
         (tokens (cdr chars) nil (if word (cons (implode (reverse word)) acc) acc)))
        (else (tokens (cdr chars) (cons (car chars) word) acc))))

(define nouns '((BLOCK BLOCK) (BLOCKS BLOCK) (CUBE CUBE) (CUBES CUBE)
                (PYRAMID PYRAMID) (PYRAMIDS PYRAMID) (BOX BOX) (TABLE TABLE)))
(define adjectives '((RED RED) (GREEN GREEN) (BLUE BLUE) (BIG LARGE)
                     (LARGE LARGE) (SMALL SMALL) (LITTLE SMALL)))

; a noun phrase: returns (phrase . rest of the words), or nil.  A phrase
; is (IT), (THEM), (HELD), (TOLD) or (NP det adjectives noun relation words)
(define (np ws)
  (cond ((null ws) nil)
        ((eq (car ws) 'IT) (cons '(IT) (cdr ws)))
        ((eq (car ws) 'THEM) (cons '(THEM) (cdr ws)))
        ((prefix '(THE ONE YOU ARE HOLDING) ws) (cons '(HELD) (nthcdr 5 ws)))
        ((prefix '(THE ONE WHICH I TOLD YOU TO PICK UP) ws)
         (cons '(TOLD) (nthcdr 9 ws)))
        ((member (car ws) '(A AN THE)) (np-adj (car ws) nil (cdr ws) ws))
        (else nil)))

(define (np-adj det adjs ws start)
  (cond ((null ws) nil)
        ((assoc (car ws) adjectives)
         (np-adj det (cons (cadr (assoc (car ws) adjectives)) adjs) (cdr ws) start))
        ((assoc (car ws) nouns)
         (let ((noun (cadr (assoc (car ws) nouns))) (rest (cdr ws)))
           (if (and (prefix '(WHICH IS) rest)
                    (member (caddr rest) '(TALLER NARROWER WIDER SHORTER))
                    (eq (nth 4 rest) 'THAN))
               (let ((inner (np (nthcdr 4 rest))))
                 (cons (list 'NP det adjs noun (list (caddr rest) (car inner))
                             (upto start (cdr inner)))
                       (cdr inner)))
               (cons (list 'NP det adjs noun nil (upto start rest)) rest))))
        (else nil)))

(define (prefix p ws)
  (cond ((null p) t) ((null ws) nil)
        ((eq (car p) (car ws)) (prefix (cdr p) (cdr ws))) (else nil)))
(define (nthcdr n l) (if (= n 0) l (nthcdr (- n 1) (cdr l))))
; the words of ws before the tail rest
(define (upto ws rest)
  (if (or (null ws) (eq ws rest)) nil (cons (car ws) (upto (cdr ws) rest))))

; the sentence patterns: NP marks a noun phrase, N a bare noun
(define patterns
  '(((PICK UP NP) PICKUP) ((GRASP NP) PICKUP)
    ((FIND NP AND PUT IT INTO NP) FINDPUT)
    ((WHAT DOES NP CONTAIN) CONTAIN)
    ((WHAT IS NP SUPPORTED BY) SUPPORTER)
    ((HOW MANY N ARE NOT IN NP) HOWMANY)
    ((IS AT LEAST ONE OF THEM NARROWER THAN NP) NARROWER)
    ((IS IT SUPPORTED) SUPPORTED)
    ((CAN NP PICK UP N) CANPICK)
    ((CAN A N BE SUPPORTED BY A N) CANBESUP)
    ((CAN A N SUPPORT A N) CANSUP)
    ((STACK UP TWO N) STACK)))

; match a pattern: the list of the phrases found, or FAIL
(define (fit pat ws)
  (cond ((null pat) (if (null ws) nil 'FAIL))
        ((null ws) 'FAIL)
        ((eq (car pat) 'NP)
         (let ((r (np ws)))
           (if (null r) 'FAIL
               (let ((more (fit (cdr pat) (cdr r))))
                 (if (eq more 'FAIL) 'FAIL (cons (car r) more))))))
        ((eq (car pat) 'N)
         (if (assoc (car ws) nouns)
             (let ((more (fit (cdr pat) (cdr ws))))
               (if (eq more 'FAIL) 'FAIL (cons (cadr (assoc (car ws) nouns)) more)))
             'FAIL))
        ((eq (car pat) (car ws)) (fit (cdr pat) (cdr ws)))
        (else 'FAIL)))

(define (parse ws pats)
  (cond ((null pats) nil)
        (else (let ((r (fit (car (car pats)) ws)))
                (if (eq r 'FAIL) (parse ws (cdr pats))
                    (cons (cadr (car pats)) r))))))

; ----------------------------------------------------------------------
;  what the words refer to
; ----------------------------------------------------------------------
(define (kind-ok x noun)
  (cond ((eq noun 'CUBE) (cube x))
        (else (eq (shape x) noun))))

(define (adj-ok x adjs)
  (cond ((null adjs) t)
        ((or (eq (car adjs) (colour x)) (eq (car adjs) (size x)))
         (adj-ok x (cdr adjs)))
        (else nil)))

(define (rel-ok x rel)
  (if (null rel) t
      (let ((y (refer (cadr rel))))
        (and (atom y) y
             (let ((r (car rel)))
               (cond ((eq r 'TALLER) (> (height x) (height y)))
                     ((eq r 'SHORTER) (< (height x) (height y)))
                     ((eq r 'NARROWER) (< (width x) (width y)))
                     (else (> (width x) (width y)))))))))

(define (candidates p)
  (filter (lambda (x) (and (kind-ok x (nth 4 p)) (adj-ok x (nth 3 p)) (rel-ok x (nth 5 p))
                           (not (eq x holding))))
          (mapcar car objects)))

; one object, or (AMBIGUOUS noun) or (NONE noun)
(define (refer p)
  (cond ((eq (car p) 'IT) it)
        ((eq (car p) 'HELD) holding)
        ((eq (car p) 'TOLD) told)
        ((eq (car p) 'THEM) them)
        (else
         (let ((cs (if (eq (nth 4 p) 'BLOCK) (with-held p) (candidates p))))
           (cond ((null cs) (list 'NONE (nth 4 p)))
                 ((eq (nth 2 p) 'THE)
                  (cond ((null (cdr cs)) (car cs))
                        (else (let ((f (filter (lambda (x) (member x focus)) cs)))
                                (if (and f (null (cdr f))) (car f)
                                    (list 'AMBIGUOUS (nth 4 p)))))))
                 (else (car cs)))))))

; a block described may be the one in the hand
(define (with-held p)
  (let ((cs (candidates p)))
    (if (and holding (kind-ok holding (nth 4 p)) (adj-ok holding (nth 3 p))
             (rel-ok holding (nth 5 p)))
        (append cs (list holding)) cs)))

; ----------------------------------------------------------------------
;  names: the shortest description that fits only this object
; ----------------------------------------------------------------------
(define (noun-of x) (if (cube x) 'CUBE (shape x)))
(define (fits-desc y desc)
  (and (kind-ok y (car (last-pair desc))) (adj-ok y (butlast desc))))
(define (last-pair l) (if (null (cdr l)) l (last-pair (cdr l))))
(define (butlast l) (if (null (cdr l)) nil (cons (car l) (butlast (cdr l)))))
(define (unique desc)
  (null (cdr (filter (lambda (y) (fits-desc y desc)) (mapcar car objects)))))
(define (name x)
  (cond ((eq x 'TABLE) '(THE TABLE))
        ((eq x 'BOX) '(THE BOX))
        ((unique (list (colour x) (noun-of x))) (list 'THE (colour x) (noun-of x)))
        (else (list 'THE (size x) (colour x) (noun-of x)))))

(define (names xs)
  (cond ((null xs) nil)
        ((null (cdr xs)) (name (car xs)))
        ((null (cddr xs)) (append (name (car xs)) (cons 'AND (name (cadr xs)))))
        (else (append (name (car xs)) (names (cdr xs))))))

; ----------------------------------------------------------------------
;  the arm
; ----------------------------------------------------------------------
(define (report words) (prin1 space) (prin1 space) (prin1 space) (say words))

(define (tops x) (filter (lambda (y) (eq (on y) x)) (mapcar car support)))

(define (set-on x y)
  (setq support (cons (list x y) (filter (lambda (p) (not (eq (car p) x))) support))))

(define (put-down)
  (if holding
      (progn (set-on holding 'TABLE)
             (report (append '(I PUT) (append (name holding) '(ON THE TABLE))))
             (setq holding nil))
      nil))

(define (clear x)
  (mapcar (lambda (y) (get-rid-of y)) (tops x)))

(define (get-rid-of y)
  (grasp y)
  (put-down))

(define (grasp x)
  (if (eq holding x) nil
      (progn
       (put-down)
       (clear x)
       (setq support (filter (lambda (p) (not (eq (car p) x))) support))
       (setq holding x)
       (report (append '(I PICK UP) (name x))))))

; put x on or into y: false if the robot cannot
(define (put-on x y)
  (cond ((eq (shape y) 'PYRAMID) nil)
        (else
         (grasp x)
         (if (not (member (shape y) '(BOX TABLE))) (clear y) nil)
         (set-on x y)
         (setq holding nil)
         (report (append '(I PUT) (append (name x) (cons (if (eq y 'BOX) 'INTO 'ON) (name y)))))
         t)))

; ----------------------------------------------------------------------
;  answering
; ----------------------------------------------------------------------
(define numbers '(NONE ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE))
(define comma (car (explode ",")))
(define stop (car (explode ".")))
(define quote-mark (car (explode "'")))
(define (tack w c) (implode (append (explode w) (list c))))
; end a list of words with a mark
(define (ending ws c)
  (if (null (cdr ws)) (list (tack (car ws) c)) (cons (car ws) (ending (cdr ws) c))))

(define (object x) (and (atom x) x))
(define (trouble r)
  (cond ((eq (car r) 'AMBIGUOUS)
         (list 'I (implode (explode "DON'T")) 'UNDERSTAND 'WHICH (cadr r) 'YOU 'MEAN.))
        (else (list 'I 'SEE 'NO (cadr r) (tack 'HERE stop)))))

(define (reflect-words ws)
  (cond ((null ws) nil)
        ((prefix '(YOU ARE) ws) (cons 'I (cons 'AM (reflect-words (cddr ws)))))
        ((member (car ws) '(A AN)) (cons 'THE (reflect-words (cdr ws))))
        (else (cons (car ws) (reflect-words (cdr ws))))))

(define (answer s)
  (let ((verb (car s)) (args (cdr s)))
    (cond
     ((eq verb 'PICKUP)
      (let ((x (refer (car args))))
        (if (object x)
            (progn (grasp x) (setq told x) (setq it x) '(OK.))
            (trouble x))))
     ((eq verb 'FINDPUT)
      (let ((x (refer (car args))) (y (refer (cadr args))))
        (cond ((not (object x)) (trouble x))
              ((not (object y)) (trouble y))
              (else
               (let ((said (append (list 'BY (implode (append (list quote-mark)
                                                      (append (explode 'IT)
                                                              (list quote-mark comma))))
                                         'I 'ASSUME 'YOU 'MEAN)
                                   (ending (reflect-words (nth 6 (car args))) stop))))
                 (say said)
                 (put-on x y)
                 (setq it x)
                 '(OK.))))))
     ((eq verb 'CONTAIN)
      (let ((x (refer (car args))))
        (if (not (object x)) (trouble x)
            (let ((in (filter (lambda (y) (eq (on y) x)) (mapcar car objects))))
              (setq focus in)
              (if in (ending (names in) stop) '(NOTHING.))))))
     ((eq verb 'SUPPORTER)
      (let ((x (refer (car args))))
        (if (not (object x)) (trouble x)
            (let ((y (on x))) (setq focus (list y)) (setq it x) (ending (name y) stop)))))
     ((eq verb 'HOWMANY)
      (let ((x (refer (cadr args))))
        (let ((these (filter (lambda (y) (and (kind-ok y (car args)) (not (eq (on y) x))))
                             (mapcar car objects))))
          (setq them these)
          (list (nth (+ 1 (length these)) numbers) 'OF (tack 'THEM stop)))))
     ((eq verb 'NARROWER)
      (let ((x (refer (car args))))
        (let ((n (filter (lambda (y) (< (width y) (width x))) them)))
          (if n (progn (setq it (car n)) (append (list (tack 'YES comma)) (ending (names n) stop)))
              '(NO.)))))
     ((eq verb 'SUPPORTED)
      (let ((y (on it)))
        (if y (append (list (tack 'YES comma) 'BY) (ending (name y) stop)) '(NO.))))
     ; only the robot's hand can pick things up
     ((eq verb 'CANPICK) '(NO.))
     ((eq verb 'CANBESUP) (can-support (cadr args) (car args)))
     ((eq verb 'CANSUP) (can-support (car args) (cadr args)))
     ((eq verb 'STACK)
      (let ((cs (filter (lambda (y) (kind-ok y (car args))) (mapcar car objects))))
        (if (and cs (cdr cs) (put-on (car cs) (cadr cs)))
            '(OK.)
            (progn
             (setq learned (cons (list (car args) (car args)) learned))
             (list 'I (tack (implode (explode "CAN'T")) stop))))))
     (else '(I DO NOT UNDERSTAND.)))))

; three answers: an example in the world, a reason against, or neither
(define (can-support lower upper)
  (cond ((filter (lambda (y) (and (kind-ok y upper) (on y) (kind-ok (on y) lower)))
                 (mapcar car support))
         '(YES.))
        ((member (list lower upper) learned) '(NO -- I HAVE TRIED.))
        (else (list 'I (implode (explode "DON'T")) (tack 'KNOW stop)))))

(define (tell text)
  (prin1 text) (terpri)
  (let ((s (parse (tokens (explode text) nil nil) patterns)))
    (say (if s (answer s) '(I DO NOT UNDERSTAND.))))
  (terpri))

(say '(MICRO-SHRDLU))
(terpri)
(tell "PICK UP A BIG RED BLOCK.")
(tell "GRASP THE PYRAMID.")
(tell "FIND A BLOCK WHICH IS TALLER THAN THE ONE YOU ARE HOLDING AND PUT IT INTO THE BOX.")
(tell "WHAT DOES THE BOX CONTAIN?")
(tell "WHAT IS THE PYRAMID SUPPORTED BY?")
(tell "HOW MANY BLOCKS ARE NOT IN THE BOX?")
(tell "IS AT LEAST ONE OF THEM NARROWER THAN THE ONE WHICH I TOLD YOU TO PICK UP?")
(tell "IS IT SUPPORTED?")
(tell "CAN THE TABLE PICK UP BLOCKS?")
(tell "CAN A PYRAMID BE SUPPORTED BY A BLOCK?")
(tell "CAN A PYRAMID SUPPORT A PYRAMID?")
(tell "STACK UP TWO PYRAMIDS.")
(say '(AND ONE EXCHANGE NOT IN WINOGRAD -- ASKED AGAIN AFTER TRYING:))
(terpri)
(tell "CAN A PYRAMID SUPPORT A PYRAMID?")
