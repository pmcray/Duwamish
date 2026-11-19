; ======================================================================
;  STRIPS -- after Fikes and Nilsson (SRI, 1971), for Shakey the robot
;
;  The world is a list of facts.  An operator has a list of
;  preconditions, a list of facts it deletes and a list it adds; ?x is a
;  variable.  To achieve a goal STRIPS looks for an operator whose add
;  list contains it, makes that operator's preconditions its new goals,
;  and so on down, applying each operator when its preconditions hold.
;
;  Shakey is in room 3.  A box is in room 1.  The light switch in room 2
;  is too high to reach.  The goal is the light on.  Afterwards, the plan
;  is carried out step by step on a copy of the world, checking every
;  precondition, to show that it really works.
; ======================================================================

(define world
  '((INROOM ROBOT ROOM3) (ONFLOOR)
    (INROOM BOX1 ROOM1) (PUSHABLE BOX1) (CLIMBABLE BOX1)
    (INROOM LS2 ROOM2) (TYPE LS2 LIGHTSWITCH) (STATUS LS2 OFF)
    (INROOM D12 ROOM1) (INROOM D12 ROOM2) (INROOM D23 ROOM2) (INROOM D23 ROOM3)
    (CONNECTS D12 ROOM1 ROOM2) (CONNECTS D12 ROOM2 ROOM1)
    (CONNECTS D23 ROOM2 ROOM3) (CONNECTS D23 ROOM3 ROOM2)))

; (name parameters preconditions deletions additions)
(define operators
  '((GOTO (?X)
     ((INROOM ROBOT ?R) (INROOM ?X ?R) (ONFLOOR))
     ((NEXTTO ROBOT ?ANY))
     ((NEXTTO ROBOT ?X)))
    (GOTHRU (?D ?R1 ?R2)
     ((CONNECTS ?D ?R1 ?R2) (INROOM ROBOT ?R1) (NEXTTO ROBOT ?D) (ONFLOOR))
     ((INROOM ROBOT ?R1) (NEXTTO ROBOT ?ANY))
     ((INROOM ROBOT ?R2)))
    (PUSH (?B ?X ?R)
     ((PUSHABLE ?B) (INROOM ?X ?R) (INROOM ?B ?R) (INROOM ROBOT ?R)
      (NEXTTO ROBOT ?B) (ONFLOOR))
     ((NEXTTO ?B ?ANY) (NEXTTO ROBOT ?ANY2))
     ((NEXTTO ?B ?X) (NEXTTO ROBOT ?B)))
    (PUSHTHRU (?B ?D ?R1 ?R2)
     ((PUSHABLE ?B) (INROOM ?B ?R1) (CONNECTS ?D ?R1 ?R2) (INROOM ROBOT ?R1)
      (NEXTTO ?B ?D) (NEXTTO ROBOT ?B) (ONFLOOR))
     ((INROOM ROBOT ?R1) (INROOM ?B ?R1) (NEXTTO ?B ?ANY) (NEXTTO ROBOT ?ANY2))
     ((INROOM ROBOT ?R2) (INROOM ?B ?R2) (NEXTTO ROBOT ?B)))
    (CLIMBON (?B)
     ((CLIMBABLE ?B) (NEXTTO ROBOT ?B) (ONFLOOR))
     ((ONFLOOR))
     ((ON ROBOT ?B)))
    (TURNON (?S ?B)
     ((TYPE ?S LIGHTSWITCH) (CLIMBABLE ?B) (NEXTTO ?B ?S) (ON ROBOT ?B))
     ((STATUS ?S OFF))
     ((STATUS ?S ON)))))

; ----------------------------------------------------------------------
;  variables, bindings and matching
; ----------------------------------------------------------------------
; ?X is written for readability; on loading, each is turned into one
; shared cell (VAR ?X), so that telling a variable is one EQ, not an
; EXPLODE of its name every time
(define qmark (car (explode "?")))
(define varcells nil)
(define (var-cell name)
  (let ((p (assoc name varcells)))
    (if p (cadr p)
        (let ((c (list 'VAR name)))
          (setq varcells (cons (list name c) varcells))
          c))))
(define (prep x)
  (cond ((consp x) (cons (prep (car x)) (prep (cdr x))))
        ((and (symbolp x) x (eq (car (explode x)) qmark)) (var-cell x))
        (else x)))
(setq operators (prep operators))

(define (var x) (and (consp x) (eq (car x) 'VAR)))
(define (assq k l)
  (cond ((null l) nil) ((eq k (car (car l))) (car l)) (else (assq k (cdr l)))))

(define (value x b)
  (let ((p (and (var x) (assq x b))))
    (if p (value (cadr p) b) x)))

(define (subst x b)
  (cond ((var x) (value x b))
        ((consp x) (cons (subst (car x) b) (subst (cdr x) b)))
        (else x)))

; match a pattern (with variables) against a ground fact: new bindings,
; or FAIL
(define (unify p f b)
  (cond ((eq b 'FAIL) 'FAIL)
        ((and (null p) (null f)) b)
        ((or (null p) (null f)) 'FAIL)
        (else (let ((x (value (car p) b)))
                (cond ((var x) (unify (cdr p) (cdr f) (cons (list x (car f)) b)))
                      ((eq x (car f)) (unify (cdr p) (cdr f) b))
                      (else 'FAIL))))))

; every way the literal g holds in the state
(define (matches g b facts)
  (cond ((null facts) nil)
        ((not (eq (car g) (car (car facts)))) (matches g b (cdr facts)))
        (else (let ((b2 (unify g (car facts) b)))
                (if (eq b2 'FAIL) (matches g b (cdr facts))
                    (cons b2 (matches g b (cdr facts))))))))

(define (ground x b)
  (cond ((var x) (not (var (value x b))))
        ((consp x) (and (ground (car x) b) (ground (cdr x) b)))
        (else t)))

; ----------------------------------------------------------------------
;  applying an operator: deletions may hold variables, which match
;  anything
; ----------------------------------------------------------------------
(define (delete-all dels state b)
  (cond ((null dels) state)
        (else (delete-all (cdr dels)
                          (filter (lambda (f) (eq (unify (subst (car dels) b) f nil) 'FAIL))
                                  state)
                          b))))

(define (apply-op op b state)
  (append (mapcar (lambda (a) (subst a b)) (nth 5 op))
          (delete-all (nth 4 op) state b)))

; ----------------------------------------------------------------------
;  the planner.  achieve returns (state bindings plan), or nil
; ----------------------------------------------------------------------
(define nodes 0)

(define (achieve goals b state depth)
  (cond ((null goals) (list state b nil))
        (else (achieve1 (car goals) (cdr goals) b state depth))))

(define (achieve1 g rest b state depth)
  (or (try-matches (matches g b state) rest state depth)
      (and (ground g b) (> depth 0)
           (try-ops (subst g b) g rest b state depth operators))))

(define (try-matches bs rest state depth)
  (cond ((null bs) nil)
        (else (or (achieve rest (car bs) state depth)
                  (try-matches (cdr bs) rest state depth)))))

; an operator whose additions include g; achieve its preconditions, apply
; it, and go on -- checking g again, since the subplan may have undone it
(define (try-ops gg g rest b state depth ops)
  (cond ((null ops) nil)
        (else
         (or (try-adds gg g rest b state depth (car ops) (nth 5 (car ops)))
             (try-ops gg g rest b state depth (cdr ops))))))

(define (try-adds gg g rest b state depth op adds)
  (cond ((null adds) nil)
        (else
         (let ((e (unify (car adds) gg nil)))
           (or (and (not (eq e 'FAIL)) (use-op gg g rest b state depth op e))
               (try-adds gg g rest b state depth op (cdr adds)))))))

(define (use-op gg g rest b state depth op e)
  (setq nodes (+ nodes 1))
  (let ((sub (achieve (nth 3 op) e state (- depth 1))))
    (and sub
         (let ((e2 (cadr sub)) (s1 (car sub)))
           ; the preconditions must all still hold
           (and (achieve (nth 3 op) e2 s1 0)
                (let ((rest-result (achieve (cons g rest) b (apply-op op e2 s1) depth)))
                  (and rest-result
                       (list (car rest-result) (cadr rest-result)
                             (append (caddr sub)
                                     (cons (cons (car op) (subst (cadr op) e2))
                                           (caddr rest-result)))))))))))

(define (all-hold goals b state)
  (cond ((null goals) t)
        ((matches (subst (car goals) b) nil state) (all-hold (cdr goals) b state))
        (else nil)))

; ----------------------------------------------------------------------
;  carrying the plan out, checking each step
; ----------------------------------------------------------------------
(define (find-op name) (assoc name operators))

(define (execute plan state n)
  (cond ((null plan) state)
        (else
         (let ((op (find-op (car (car plan)))))
           (let ((b (bind (cadr op) (cdr (car plan)) nil)))
             (let ((ok (achieve (nth 3 op) b state 0)))
               (prin1 n) (prin1 space)
               (say (cons (car (car plan)) (cdr (car plan))))
               (if ok (execute (cdr plan) (apply-op op b state) (+ n 1))
                   (progn (say '(*** A PRECONDITION DOES NOT HOLD)) nil))))))))

; bind the operator's parameters; the other variables by the world
(define (bind params args b)
  (if (null params) b (bind (cdr params) (cdr args) (cons (list (car params) (car args)) b))))

(define (plan-for goal depth)
  (setq nodes 0)
  (achieve (list goal) nil world depth))

(say '(STRIPS AND SHAKEY))
(terpri)
(say '(THE WORLD:))
(mapcar (lambda (f) (prin1 space) (prin1 space) (say f)) world)
(terpri)
(say '(THE GOAL: (STATUS LS2 ON)))
(define result (plan-for '(STATUS LS2 ON) 6))
(say (list 'PLANNED 'WITH nodes 'OPERATOR 'CHOICES))
(terpri)
(say '(SHAKEY CARRIES OUT THE PLAN:))
(define after (execute (caddr result) world 1))
(terpri)
(if (and after (matches '(STATUS LS2 ON) nil after))
    (say '(THE LIGHT IS ON.))
    (say '(THE PLAN FAILED.)))
(say '(SHAKEY ENDS WHERE?))
(mapcar (lambda (f) (if (eq (cadr f) 'ROBOT) (progn (prin1 space) (prin1 space) (say f)) nil))
        after)
